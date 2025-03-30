#!/usr/bin/env python3
import subprocess
import time
import re
import queue
import threading
import json
from flask import Flask, jsonify, request

app = Flask(__name__)

# Global scanning state and discovered devices
device_queue = queue.Queue()
scanning = False
seen_devices = {}
scan_process = None


def remove_ansi(text):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

@app.route("/start-scan")
def start_scan():
    global scanning
    if scanning:
        return jsonify({"message": "Already scanning."}), 200
    scanning = True
    threading.Thread(target=scan_devices_background, daemon=True).start()
    return jsonify({"message": "Scan started."}), 200


@app.route("/stop-scan")
def stop_scan():
    global scanning, scan_process
    scanning = False
    try:
        if scan_process and scan_process.stdin:
            scan_process.stdin.write("scan off\n")
            scan_process.stdin.flush()
            time.sleep(1)
            scan_process.kill()
            scan_process = None
            print("DEBUG: Scan stopped and bluetoothctl process killed.")
    except Exception as e:
        print("Error in /stop-scan:", e)
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Scanning stopped."})




@app.route("/device-queue")
def device_queue_api():
    global seen_devices
    while not device_queue.empty():
        mac, name = device_queue.get()
        seen_devices[mac] = name
    return jsonify(seen_devices)





def scan_devices_background():
    global scanning, scan_process
    scan_process = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        universal_newlines=True
    )
    scan_process.stdin.write("agent on\n")
    scan_process.stdin.write("default-agent\n")
    scan_process.stdin.write("scan on\n")
    scan_process.stdin.flush()
    try:
        while scanning:
            line = scan_process.stdout.readline()
            if "NEW" in line:
                clean = remove_ansi(line.strip())
                parts = clean.split()
                if len(parts) >= 4:
                    mac = parts[2]
                    display_name = " ".join(parts[3:])
                    if re.search(r'([0-9A-F]{2}-){2,}', display_name, re.IGNORECASE):
                        print(f"DEBUG: Filtering out device: {display_name}")
                    else:
                        device_queue.put((mac, display_name))
                        print(f"DEBUG: Adding device: {mac} with name: {display_name}")
    except Exception as e:
        print("Scan error:", e)
    finally:
        scanning = False
        if scan_process and scan_process.stdin:
            scan_process.stdin.write("scan off\n")
            scan_process.stdin.flush()
        if scan_process:
            scan_process.kill()
            scan_process = None




@app.route("/pair", methods=["POST"])
def api_pair():
    data = request.get_json()
    if not data or "devices" not in data:
        return jsonify({"error": "Missing 'devices' field in JSON body"}), 400
    config_id = data.get("configID", "defaultID")
    config_name = data.get("configName", "defaultName")
    devices = data["devices"]
    settings = data.get("settings", {})
    try:
        cmd = [
            "./connect_configuration.sh",
            str(config_id),
            config_name,
            json.dumps(devices),
            json.dumps(settings)
        ]
        subprocess.run(cmd, check=True)
        return jsonify({"message": "Pairing process completed successfully."})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/volume", methods=["POST"])
def api_volume():
    data = request.get_json()
    if not data or "mac" not in data or "volume" not in data:
        return jsonify({"error": "Missing 'mac' or 'volume' field"}), 400
    mac = data["mac"]
    volume = data["volume"]
    sink_name = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
    try:
        subprocess.run(["pactl", "set-sink-volume", sink_name, f"{volume}%"], check=True)
        return jsonify({"message": f"Volume for {mac} set to {volume}%."})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/latency", methods=["POST"])
def api_latency():
    data = request.get_json()
    if not data or "mac" not in data or "latency" not in data:
        return jsonify({"error": "Missing 'mac' or 'latency' field"}), 400
    mac = data["mac"]
    latency = data["latency"]
    try:
        subprocess.run(["./set_latency.sh", mac, str(latency)], check=True)
        return jsonify({"message": f"Latency for {mac} set to {latency} ms."})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/connect", methods=["POST"])
def api_connect():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400
    required_fields = ["configID", "configName", "speakers", "settings"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    config_id = data["configID"]
    config_name = data["configName"]
    speakers = data["speakers"]
    settings = data["settings"]

    try:
        cmd = [
            "./connect_configuration.sh",
            str(config_id),
            config_name,
            json.dumps(speakers),
            json.dumps(settings)
        ]
        subprocess.run(cmd, check=True)
        return jsonify({"message": "Configuration connected successfully."})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/disconnect", methods=["POST"])
def api_disconnect():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400
    required_fields = ["configID", "configName", "speakers", "settings"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    config_id = data["configID"]
    config_name = data["configName"]
    speakers = data["speakers"]
    settings = data["settings"]

    try:
        cmd = [
            "./disconnect_configuration.sh",
            str(config_id),
            config_name,
            json.dumps(speakers),
            json.dumps(settings)
        ]
        subprocess.run(cmd, check=True)
        return jsonify({"message": "Configuration disconnected successfully."})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/paired-devices", methods=["GET"])
def api_paired_devices():
    try:
        devices = {}

        # Step 1: Get list of all Bluetooth controllers
        list_output = subprocess.check_output(
            ["bluetoothctl", "list"],
            universal_newlines=True
        )

        controller_macs = []
        for line in list_output.splitlines():
            if line.startswith("Controller"):
                parts = line.strip().split()
                if len(parts) >= 2:
                    controller_macs.append(parts[1])  # e.g., BC:FC:E7:21:1A:0B

        # Step 2: For each controller, list paired devices
        for ctrl_mac in controller_macs:
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            proc.stdin.write(f"select {ctrl_mac}\n")
            proc.stdin.write("devices Paired\n")
            proc.stdin.write("exit\n")
            proc.stdin.flush()

            output, _ = proc.communicate(timeout=3)

            for line in output.splitlines():
                clean_line = remove_ansi(line).strip()
                if clean_line.startswith("Device"):
                    parts = clean_line.split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        display_name = " ".join(parts[2:]).strip()
                        devices[mac] = display_name

        return jsonify(devices)

    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500





if __name__ == '__main__':
    app.run(host="0.0.0.0", port=3000)
