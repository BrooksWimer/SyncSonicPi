from flask import request, jsonify
from pydbus import SystemBus
from utils.bluetooth import get_managed_objects, get_adapter_by_address, get_device_by_address, disconnect_device, is_device_connected
from utils.logging import log, RED, ENDC
import subprocess
import json
import time
import os

# def api_disconnect():
#     data = request.get_json()
#     if not data:
#         return jsonify({"error": "Missing JSON data"}), 400

#     required_fields = ["configID", "configName", "speakers", "settings"]
#     for field in required_fields:
#         if field not in data:
#             return jsonify({"error": f"Missing field: {field}"}), 400

#     speakers = data["speakers"]  # format: { mac: name }

#     try:
#         bus = SystemBus()
#         objects = get_managed_objects(bus)

#         results = {}
#         for mac, name in speakers.items():
#             if disconnect_device(bus, mac, objects):
#                 results[mac] = {"name": name, "result": "Disconnected"}
#             else:
#                 results[mac] = {"name": name, "result": "Failed to disconnect"}
#             time.sleep(2)

#         return jsonify(results)

#     except Exception as e:
#         log(f"❌ Error in disconnect process: {e}")
#         return jsonify({"error": str(e)}), 500


def api_disconnect():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    required_fields = ["configID", "configName", "speakers", "settings"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    speakers = data["speakers"]  # format: { mac: name }

    try:
        bus = SystemBus()
        objects = get_managed_objects(bus)
        results = {}

        for mac, name in speakers.items():
            log(f"🔌 Disconnecting {name} ({mac})")
            success = disconnect_device(bus, mac, objects)
            results[mac] = {
                "name": name,
                "result": "Disconnected" if success else "Failed to disconnect"
            }

        return jsonify(results)

    except Exception as e:
        log(f"❌ Error in disconnect process: {e}")
        return jsonify({"error": str(e)}), 500