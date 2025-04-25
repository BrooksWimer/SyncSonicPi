from flask import request, jsonify
import subprocess
import os
from utils.logging import log
from utils.pulseaudio_service import cleanup_pulseaudio

RESET_SCRIPT = "/home/syncsonic2/reset_bt_adapters.sh"
PULSE_CONFIG_DIR = "/home/syncsonic2/.config/pulse"

def api_reset_adapters():
    try:
        data = request.get_json() or {}
        deep_reset = data.get("deepReset", False)
        expected_count = str(data.get("expectedAdapterCount", 4))  # Default remains 4
    
        cleanup_pulseaudio()

        # Step 1: Reset Bluetooth adapters with passed expected count
        subprocess.run([RESET_SCRIPT, expected_count], check=True)  # add argument

        # Step 2: Kill lingering processes
        subprocess.run(["pkill", "-f", "bluetoothctl"], check=False)
        subprocess.run(["pkill", "-f", "pulseaudio"], check=False)

        # Step 3: Restart Bluetooth service
        subprocess.run(["sudo", "systemctl", "restart", "bluetooth"], check=True)

        # Step 4: PulseAudio cleanup
        if deep_reset:
            if os.path.isdir(PULSE_CONFIG_DIR):
                log(f"doing hard reset")
                subprocess.run(["sudo", "systemctl", "stop", "bluetooth"], check=True)
                subprocess.run(["pkill", "-f", "bluetoothd"], check=False)
                subprocess.run(["sudo", "rm", "-rf", "/var/lib/bluetooth"], check=True)
                subprocess.run(["sudo", "systemctl", "start", "bluetooth"], check=True)
                subprocess.run(["rm", "-rf", PULSE_CONFIG_DIR], check=True)
            
        subprocess.run(["sudo","systemctl","restart","bluetooth"])

        subprocess.run(["pulseaudio", "--start"], check=False)

        return jsonify({"message": f"{'Full' if deep_reset else 'Soft'} reset complete and services restarted."}), 200

    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Reset script or service failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
