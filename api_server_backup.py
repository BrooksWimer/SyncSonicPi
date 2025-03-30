#!/usr/bin/env python3
import subprocess
import time
import re
import queue
import threading
import json
from flask import Flask, jsonify, request

app = Flask(__name__)

def remove_ansi(text):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)



device_queue = queue.Queue()
scanning = False

@app.route("/start-scan")
def start_scan():
    global scanning
    if scanning:
        return jsonify({"message": "Already scanning."}), 200
    scanning = True
    threading.Thread(target=scan_devices_background, daemon=True).start()
    return jsonify({"message": "Scan started."}), 200

def scan_devices_background():
    global scanning
    proc = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
    proc.stdin.write("scan on\n")
    proc.stdin.flush()
    try:
        while scanning:
            line = proc.stdout.readline()
            if "NEW" in line:
                clean = remove_ansi(line.strip())
                parts = clean.split()
                if len(parts) >= 4:
                    mac = parts[2]
                    name = " ".join(parts[3:])
                    device_queue.put((mac, name))
    except Exception as e:
        print("Scan error:", e)
    finally:
        scanning = False
        proc.stdin.write("scan off\n")
        proc.kill()

@app.route("/device-queue")
def device_queue_api():
    devices = {}
    while not device_queue.empty():
        mac, name = device_queue.get()
        devices[mac] = name
    return jsonify(devices)





def scan_devices():
    """
    Start a temporary bluetoothctl subprocess, enable the agent,
    turn on scanning continuously, and return the output as devices are found.
    """
    global scanning
    proc = subprocess.Popen(
        ['bluetoothctl'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    # Turn on agent and set as default
    proc.stdin.write("agent on\n")
    proc.stdin.write("default-agent\n")
    proc.stdin.write("scan on\n")
    proc.stdin.flush()

    print("Scanning for devices... (Press Ctrl+C to stop)")

    # Continuously read output
    try:
        while scanning:
            output = proc.stdout.readline()
            if output:
                clean_line = remove_ansi(output.strip())
                print("DEBUG: Found device:", clean_line)  # Log found devices
                parse_device(clean_line)  # Call a function to handle the parsing
            time.sleep(0.1)  # Sleep briefly to prevent high CPU usage
    except Exception as e:
        print("Error during scanning:", e)
    finally:
        proc.stdin.write("scan off\n")
        proc.stdin.flush()
        proc.kill()
        print("DEBUG: Scanning stopped.")

def parse_device(line):
    """
    Parses a single line of device output from bluetoothctl.
    """
    if "NEW" in line:
        parts = line.split()
        if len(parts) >= 4:
            mac = parts[2]  # e.g., "57:EE:5E:98:26:81"
            display_name = " ".join(parts[3:]).strip()

            # Check for unwanted patterns
            if re.search(r'([0-9A-F]{2}-){2,}', display_name):
                print("DEBUG: Filtering out device:", display_name)  # Log filtered out devices
            else:
                device_queue = queue.Queue()
                scanning = False

@app.route("/start-scan")
def start_scan():
    global scanning
    if scanning:
        return jsonify({"message": "Already scanning."}), 200
    scanning = True
    threading.Thread(target=scan_devices_background, daemon=True).start()
    return jsonify({"message": "Scan started."}), 200

def scan_devices_background():
    global scanning
    proc = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
    proc.stdin.write("scan on\n")
    proc.stdin.flush()
    try:
        while scanning:
            line = proc.stdout.readline()
            if "NEW" in line:
                clean = remove_ansi(line.strip())
                parts = clean.split()
                if len(parts) >= 4:
                    mac = parts[2]
                    name = " ".join(parts[3:])
                    device_queue.put((mac, name))
    except Exception as e:
        print("Scan error:", e)
    finally:
        scanning = False
        proc.stdin.write("scan off\n")
        proc.kill()

@app.route("/device-queue")
def device_queue_api():
    devices = {}
    while not device_queue.empty():
        mac, name = device_queue.get()
        devices[mac] = name
    return jsonify(devices)                # Here you can add the device to a global list or queue





# Function to start scanning in a separate thread
def start_scanning():
    global scanning
    scanning = True
    scan_thread = threading.Thread(target=scan_devices)
    scan_thread.start()

# Function to stop scanning
def stop_scanning():
    global scanning
    scanning = False

def parse_devices(scan_output):
    """
    Parses the scan output.
    For each line that contains "NEW", it extracts:
      - The MAC address (third token)
      - The display name (concatenation of tokens 4 through end)
    Also adds paired devices (if not already discovered).
    Returns a dictionary mapping MAC addresses to display names.
    """
    devices = {}
    for line in scan_output.splitlines():
        clean_line = remove_ansi(line).strip()
        print("DEBUG:", clean_line)
        if "NEW" in clean_line:
            parts = clean_line.split()
            if len(parts) >= 4:
                mac = parts[2]  # e.g., "57:EE:5E:98:26:81"
                display_name = " ".join(parts[3:]).strip()


                # Check for unwanted patterns
                if re.search(r'([0-9A-F]{2}-){2,}', display_name):
                    print("DEBUG: Filtering out device:", display_name)  # Log filtered out devices
                else:
                    devices[mac] = display_name
                    print("DEBUG: Adding device:", mac, "with name:", display_name)


    # Add paired devices
    try:
        paired_output = subprocess.check_output(
            ['bluetoothctl', 'devices', 'Paired'], universal_newlines=True
        )
        for line in paired_output.splitlines():
            clean_line = remove_ansi(line).strip()
            if clean_line.startswith("Device"):
                parts = clean_line.split()
                if len(parts) >= 3:
                    mac = parts[1]
                    display_name = " ".join(parts[2:]).strip()
                    if mac not in devices:
                        devices[mac] = display_name
    except subprocess.CalledProcessError as e:
        print("Error retrieving paired devices:", e)

    return devices

@app.route("/scan", methods=["GET"])
def api_scan():
    global scanning
    scanning = True  # Start scanning
    scan_thread = threading.Thread(target=scan_devices)
    scan_thread.start()
    
    # Log the scanning status
    print("DEBUG: Scanning started.")
    
    return jsonify({"message": "Scanning started."}), 200


@app.route("/pair", methods=["POST"])
def api_pair():
    data = request.get_json()
    if not data or "devices" not in data:
        return jsonify({"error": "Missing 'devices' field in JSON body"}), 400
    # Instead of saving to a file and calling pair_selected_devices.sh,
    # we now call connect_configuration.sh with the proper JSON arguments.
    config_id = data.get("configID", "defaultID")
    config_name = data.get("configName", "defaultName")
    devices = data["devices"]  # mapping: MAC -> display name
    # Use an empty settings dict if not provided.
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
    speakers = data["speakers"]  # mapping: mac -> name
    settings = data["settings"]  # mapping: mac -> { volume, latency }

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
        paired_output = subprocess.check_output(['bluetoothctl', 'devices', 'Paired'], universal_newlines=True)
        devices = {}
        for line in paired_output.splitlines():
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



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=3000)
