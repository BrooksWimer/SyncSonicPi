from flask import request, jsonify
from utils.logging import log
from utils.pulseaudio_service import create_loopback

def api_latency():
    data = request.get_json()
    if not data or "mac" not in data or "latency" not in data:
        return jsonify({"error": "Missing 'mac' or 'latency' field"}), 400

    mac = data["mac"]
    latency = data["latency"]

    try:
        mac_formatted = mac.replace(":", "_")
        expected_sink_prefix = f"bluez_sink.{mac_formatted}"

        log(f"🎯 Setting latency for {mac} (sink starts with {expected_sink_prefix}) to {latency} ms...")

        success = create_loopback(expected_sink_prefix, latency_ms=latency)

        if success:
            return jsonify({"message": f"Latency for {mac} set to {latency} ms."})
        else:
            return jsonify({"error": f"Failed to create loopback for {mac}"}), 500

    except Exception as e:
        log(f"🔥 Error in latency endpoint: {e}")
        return jsonify({"error": str(e)}), 500