from flask import jsonify
import subprocess
import os
import re

AUTO_CONNECT_SCRIPT = "/home/syncsonic2/auto_connect.sh"
RESERVED_FLAG_PATH = "/tmp/hci0_reserved_for_phone"


def get_mac_for_adapter(adapter="hci0"):
    try:
        # Use full path to hciconfig
        out = subprocess.check_output(["/usr/bin/hciconfig", adapter], text=True)
        print(f"🔍 Raw hciconfig output:\n{out}")
        match = re.search(r"BD Address: (\S+)", out)
        if match:
            return match.group(1)
        else:
            print("❌ Regex didn't match.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ hciconfig command failed:\n{e.output}")
    except Exception as e:
        print(f"⚠️ General exception: {e}")
    return None




def set_reserved_flag(mac):
    with open(RESERVED_FLAG_PATH, "w") as f:
        f.write(mac)

def api_connect_phone():
    try:
        result = subprocess.run([AUTO_CONNECT_SCRIPT], timeout=30)
    except subprocess.TimeoutExpired:
        subprocess.kill()
        return jsonify({"success": False, "error": "Pairing script timed out"}), 200

    if result.returncode == 0:
        mac = get_mac_for_adapter("hci0")
        if mac:
            set_reserved_flag(mac)
            return jsonify({"success": True, "message": "Phone paired successfully", "reserved_mac": mac})
        else:
            return jsonify({"success": False, "error": "Failed to get MAC for hci0"}), 500
    elif result.returncode == 2:
        return jsonify({"success": False, "error": "Phone pairing timed out"}), 408
    else:
        return jsonify({"success": False, "error": "Pairing script failed"}), 500
