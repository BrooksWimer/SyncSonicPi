from flask import request, jsonify
import subprocess
from utils.logging import log


def api_latency():
    data = request.get_json()
    if not data or "mac" not in data or "latency" not in data:
        return jsonify({"error": "Missing 'mac' or 'latency' field"}), 400

    mac = data["mac"]
    latency = str(data["latency"])
    mac_formatted = mac.replace(":", "_")
    sink_name = None

    try:

        sink_name = f"bluez_sink.{mac_formatted}.a2dp_sink"

        # ♻️ Unload any existing loopbacks targeting this sink
        list_modules = subprocess.run(["pactl", "list", "short", "modules"], capture_output=True, text=True)
        if list_modules.returncode != 0:
            return jsonify({"error": list_modules.stderr}), 500

        # Find all loopback modules targeting this sink
        module_ids = []
        for line in list_modules.stdout.splitlines():
            if "module-loopback" in line and sink_name in line:
                module_id = line.split()[0]
                module_ids.append(module_id)
                log(f"Found existing loopback module {module_id} for {sink_name}")

        # Unload all found modules
        for mod_id in module_ids:
            unload_result = subprocess.run(["pactl", "unload-module", mod_id], capture_output=True, text=True)
            if unload_result.returncode == 0:
                log(f"✅ Unloaded loopback module {mod_id} for {sink_name}")
            else:
                log(f"⚠️ Failed to unload module {mod_id}: {unload_result.stderr}")

        # 🎛️ Load new loopback with latency
        load_cmd = [
            "pactl", "load-module", "module-loopback",
            f"sink={sink_name}",
            f"latency_msec={latency}"
        ]
        result = subprocess.run(load_cmd, capture_output=True, text=True)

        if result.returncode != 0 or not result.stdout.strip():
            log(f"❌ Failed to load loopback: {result.stderr}")
            return jsonify({"error": result.stderr}), 500

        log(f"✅ Loaded loopback for {mac} on {sink_name} with latency {latency} ms")
        return jsonify({"message": f"Latency for {mac} set to {latency} ms."})

    except Exception as e:
        log(f"🔥 Error in latency endpoint: {e}")
        return jsonify({"error": str(e)}), 500