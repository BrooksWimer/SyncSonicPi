from flask import request, jsonify
import subprocess
from utils.logging import log, RED, GREEN, ENDC

def set_volume(mac: str, volume: int) -> bool:
    """
    Sets the volume for a Bluetooth audio sink corresponding to the given MAC address.
    Returns True if successful, False otherwise.
    """
    try:
        mac_formatted = mac.replace(':', '_')
        sink_name = f"bluez_sink.{mac_formatted}.a2dp_sink"

        result = subprocess.run(
            ["pactl", "set-sink-volume", sink_name, f"{volume}%"],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            log(f"{GREEN}Successfully set volume for {mac} to {volume}%{ENDC}")
            return True
        else:
            log(f"{RED}Error setting volume for {mac}: {result.stderr}{ENDC}")
            return False

    except Exception as e:
        log(f"{RED}Exception in set_volume({mac}): {e}{ENDC}")
        return False

def api_volume():
    data = request.get_json()
    if not data or "mac" not in data or "volume" not in data:
        return jsonify({"error": "Missing 'mac' or 'volume' field"}), 400

    mac = data["mac"]
    volume = data["volume"]

    success = set_volume(mac, volume)
    if success:
        return jsonify({"message": f"Volume for {mac} set to {volume}%."})
    else:
        return jsonify({"error": f"Failed to set volume for {mac}"}), 500





def set_stereo_volume(mac: str, left: int, right: int) -> bool:
    sink_name = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
    result = subprocess.run(
        ["pactl", "set-sink-volume", sink_name, f"{left}%", f"{right}%"],
        capture_output=True, text=True
    )
    log(f"Setting stereo volume for {mac}: L={left}%, R={right}%")
    return result.returncode == 0

def api_set_sound_field():
    data = request.get_json()

    if not data or "mac" not in data or "balance" not in data or "volume" not in data:
        return jsonify({"error": "Missing 'mac', 'balance', or 'volume'"}), 400

    mac = data["mac"]
    balance = float(data["balance"])
    volume = int(data["volume"])

    # Compute left/right volumes
    left = round(volume * (1 - balance) if balance > 0.5 else volume)
    right = round(volume * balance if balance < 0.5 else volume)

    success = set_stereo_volume(mac, left, right)
    if success:
        return jsonify({
            "success": True,
            "message": f"Stereo volume set: L={left}%, R={right}%"
        })
    else:
        return jsonify({
            "success": False,
            "error": "Failed to set stereo volume with pactl"
        }), 500
