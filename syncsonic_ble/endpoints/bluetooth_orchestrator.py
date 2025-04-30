# endpoints/bluetooth_orchestrator.py
from flask import request, jsonify
from syncsonic_ble.svc_singleton import service
from syncsonic_ble.flow.connection_service import Intent

# /connect-one  -------------------------------------------------
def api_connect_one():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify(error="missing JSON"), 400

    try:
        target = data["targetSpeaker"]
        payload = {
            "mac":     target["mac"],
            "friendly_name": target.get("name", ""),
            "allowed": list(data.get("settings", {}).keys()),
        }
    except (KeyError, TypeError):
        return jsonify(error="malformed payload"), 400

    service.submit(Intent.CONNECT_ONE, payload)
    return jsonify(queued=True), 202


# /disconnect  --------------------------------------------------
def api_disconnect():
    data = request.get_json(force=True, silent=True)
    if not data or "mac" not in data:
        return jsonify(error="missing mac"), 400

    service.submit(Intent.DISCONNECT, {"mac": data["mac"]})
    return jsonify(queued=True), 202
