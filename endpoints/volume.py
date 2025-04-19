from flask import request, jsonify
import subprocess
from utils.logging import log, RED, GREEN, ENDC


from flask import request, jsonify
import subprocess
from utils.logging import log, RED, GREEN, ENDC

def set_stereo_volume(mac: str, balance: int, volume: int) -> bool:
    # Clamp balance to [0.0, 1.0]
    balance = max(0.0, min(1.0, balance))

    # Compute left/right volumes based on balance
    left = round(volume * (1 - balance) * 2) if balance >= 0.5 else volume
    right = round(volume * balance * 2) if balance <= 0.5 else volume

    # Optional: clamp to 0–150% to avoid out-of-bounds
    left = min(max(left, 0), 150)
    right = min(max(right, 0), 150)
    sink_name = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
    result = subprocess.run(
        ["pactl", "set-sink-volume", sink_name, f"{left}%", f"{right}%"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        log(f"{GREEN}Set stereo volume for {mac}: L={left}%, R={right}%{ENDC}")
    else:
        log(f"{RED}Error setting stereo volume for {mac}: {result.stderr.strip()}{ENDC}")
    return result.returncode == 0, left, right

def api_volume():
    data = request.get_json()
    if not data or "mac" not in data or "volume" not in data:
        return jsonify({"error": "Missing 'mac' or 'volume' field"}), 400

    mac = data["mac"]
    volume = int(data["volume"])
    balance = float(data.get("balance", 0.5))  # Default to center balance



    success, left, right = set_stereo_volume(mac, balance, volume)
    if success:
        return jsonify({
            "success": True,
            "message": f"Volume set: Left={left}%, Right={right}%",
            "mac": mac,
            "volume": volume,
            "balance": balance
        })
    else:
        return jsonify({
            "success": False,
            "error": f"Failed to set volume for {mac}"
        }), 500

def api_mute():
    data = request.get_json()
    if not data or "mac" not in data or "mute" not in data:
        return jsonify({"error": "Missing 'mac' or 'mute' field"}), 400

    mac = data["mac"]
    mute = data["mute"]  # True to mute, False to unmute

    try:
        sinks_output = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True)
        if sinks_output.returncode != 0:
            log(f"{RED}Error getting sink list: {sinks_output.stderr}{ENDC}")
            return jsonify({"error": "Failed to get sink list"}), 500

        mac_formatted = mac.replace(':', '_')
        sink_name = None
        for line in sinks_output.stdout.splitlines():
            if mac_formatted in line:
                sink_name = line.split()[1]
                break

        if not sink_name:
            return jsonify({"error": f"No sink found for device {mac}"}), 500

        mute_flag = "1" if mute else "0"
        subprocess.run(["pactl", "set-sink-mute", sink_name, mute_flag], check=True)
        log(f"{'Muted' if mute else 'Unmuted'} speaker {mac} ({sink_name})")
        return jsonify({"message": f"{'Muted' if mute else 'Unmuted'} {mac}"})

    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Command failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500