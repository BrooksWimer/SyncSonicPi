
from flask import jsonify
import subprocess

RESET_SCRIPT = "/home/syncsonic2/reset_bt_adapters.sh"

def api_reset_adapters():
    try:
        subprocess.run([RESET_SCRIPT], check=True)
        return jsonify({"message": "Bluetooth adapters reset successfully."}), 200
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Reset script failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500