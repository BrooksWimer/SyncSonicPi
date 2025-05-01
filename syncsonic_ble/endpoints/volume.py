from flask import request, jsonify
import subprocess



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
 

    return result.returncode == 0, left, right
