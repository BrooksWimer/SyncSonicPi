from flask import request, jsonify
import subprocess
from utils.logging import log, RED, GREEN, ENDC

def api_volume():
    data = request.get_json()
    if not data or "mac" not in data or "volume" not in data:
        return jsonify({"error": "Missing 'mac' or 'volume' field"}), 400

    mac = data["mac"]
    volume = data["volume"]

    try:
        # # First, get all sinks to find the correct sink name
        # sinks_output = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True)
        # if sinks_output.returncode != 0:
        #     log(f"Error getting sink list: {sinks_output.stderr}")
        #     return jsonify({"error": "Failed to get sink list"}), 500

        # # Try different sink name formats
        # sink_name = None
        # mac_formatted = mac.replace(':', '_')

        # for line in sinks_output.stdout.splitlines():
        #     if mac_formatted in line:
        #         sink_name = line.split()[1]
        #         break

        # if not sink_name:
        #     log(f"No sink found for device {mac}")
        #     return jsonify({"error": f"No sink found for device {mac}"}), 500

        # log(f"Found sink {sink_name} for device {mac}")
        mac_formatted = mac.replace(':', '_')
        sink_name = f"bluez_output.{mac_formatted}.1"

        # Set the volume
        volume_result = subprocess.run(["pactl", "set-sink-volume", sink_name, f"{volume}%"], capture_output=True, text=True)
        if volume_result.returncode != 0:
            log(f"Error setting volume: {volume_result.stderr}")
            return jsonify({"error": f"Failed to set volume: {volume_result.stderr}"}), 500

        log(f"Successfully set volume for {mac} to {volume}%")
        return jsonify({"message": f"Volume for {mac} set to {volume}%."})

    except Exception as e:
        log(f"Error in volume endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500
