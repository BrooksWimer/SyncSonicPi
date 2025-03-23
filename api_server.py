#!/usr/bin/env python3
import subprocess
import time
import re
from flask import Flask, jsonify, request

app = Flask(__name__)

def remove_ansi(text):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

def scan_devices(scan_duration=10):
    """
    Start a temporary bluetoothctl subprocess, enable the agent,
    turn on scanning for a fixed duration, then stop scanning.
    Returns the complete scan output as a string.
    """
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
    print("Scanning for devices for {} seconds...".format(scan_duration))
    time.sleep(scan_duration)
    proc.stdin.flush()
    time.sleep(2)  # Give a moment for scanning to stop
    try:
        output, _ = proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate()
    return output

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
                display_name = ""
                for part in range(3, len(parts)):
                     display_name += parts[part] + " "
                devices[mac] = display_name.strip()
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
    raw_output = scan_devices(scan_duration=10)
    devices = parse_devices(raw_output)
    # Return JSON with discovered devices and raw output (if needed for debugging)
    return jsonify({"devices": devices, "raw": raw_output})

@app.route("/pair", methods=["POST"])
def api_pair():
    data = request.get_json()
    if not data or "devices" not in data:
        return jsonify({"error": "Missing 'devices' field in JSON body"}), 400
    # data["devices"] should be a dictionary mapping MAC addresses to display names.
    selected_devices = data["devices"]
    # Save the selected devices to a file for your pairing script.
    with open("selected_devices.txt", "w") as f:
        for mac, name in selected_devices.items():
            f.write(f"{mac},{name}\n")
    # Call your existing pairing script.
    try:
        subprocess.run(["./pair_selected_devices.sh"], check=True)
        return jsonify({"message": "Pairing process completed successfully."})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500

# Placeholder endpoints for adjusting volume and latency can be added similarly.
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
    # For adjusting latency, you would integrate your existing set_latency logic.
    # Here, we'll assume a placeholder implementation.
    mac = data["mac"]
    latency = data["latency"]
    try:
        # Example: call a shell script that sets latency for the given MAC.
        subprocess.run(["./set_latency.sh", mac, str(latency)], check=True)
        return jsonify({"message": f"Latency for {mac} set to {latency} ms."})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/connect", methods=["POST"])
def api_connect():
    import json
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    # Ensure required fields are provided.
    required_fields = ["configID", "configName", "speakers", "settings"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    config_id = data["configID"]
    config_name = data["configName"]
    speakers = data["speakers"]  # mapping: mac -> name
    settings = data["settings"]  # mapping: mac -> { volume, latency }

    try:
        # Build command with shell script and pass arguments as JSON strings.
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
    import json
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    # Ensure required fields are provided.
    required_fields = ["configID", "configName", "speakers", "settings"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    config_id = data["configID"]
    config_name = data["configName"]
    speakers = data["speakers"]  # mapping: mac -> name
    settings = data["settings"]  # mapping: mac -> { volume, latency }

    try:
        # Build command to call your disconnect shell script
        # Make sure that disconnect_configuration.sh exists and is executable.
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



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=3000)
