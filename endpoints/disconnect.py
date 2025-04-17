from flask import request, jsonify
from pydbus import SystemBus
from utils.logging import log, RED, ENDC
import subprocess
import json
import time
import os
from utils.global_state import update_bluetooth_state, GLOBAL_BLUETOOTH_STATE

def disconnect_device(device_mac: str, controller_mac: str = None) -> bool:
    """
    Disconnects a Bluetooth device using global state.
    If controller_mac is not provided, the function will try to infer it from state.

    Returns:
        True if disconnect was attempted, False if the device was not found or already disconnected.
    """
    device_mac = device_mac.upper()
    controller_mac = controller_mac.upper() if controller_mac else None

    # Find the controller and hci name from the global state
    found_ctrl = None
    hci_name = None

    for ctrl_mac, ctrl in GLOBAL_BLUETOOTH_STATE.get("controllers", {}).items():
        if controller_mac and ctrl_mac != controller_mac:
            continue

        if device_mac in [m.upper() for m in ctrl.get("connected", [])]:
            found_ctrl = ctrl_mac
            hci_name = ctrl.get("hci")
            break

    if not found_ctrl or not hci_name:
        log(f"❌ Could not find connected device {device_mac} in state")
        return False

    bus = SystemBus()
    device_path = f"/org/bluez/{hci_name}/dev_{device_mac.replace(':', '_')}"

    try:
        device_obj = bus.get("org.bluez", device_path)
        log(f"🔌 Disconnecting {device_mac} from {found_ctrl} ({device_path})")
        device_obj.Disconnect()
        time.sleep(0.5)
        log(f"✅ Disconnect command sent to {device_mac}")
        return True
    except Exception as e:
        log(f"❌ Failed to disconnect {device_mac}: {e}")
        return False

def api_disconnect():
    update_bluetooth_state()  # Refresh current state from all adapters

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    required_fields = ["configID", "configName", "speakers", "settings"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    speakers = data["speakers"]  # format: { mac: name }

    results = {}

    for mac, name in speakers.items():
        log(f"🔌 Disconnecting {name} ({mac})")
        success = disconnect_device(mac)
        results[mac] = {
            "name": name,
            "result": "Disconnected" if success else "Failed to disconnect"
        }

    return jsonify(results)