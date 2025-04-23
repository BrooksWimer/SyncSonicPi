from flask import request, jsonify
from pydbus import SystemBus
from utils.logging import log, RED, ENDC
import subprocess
import json
import time
import os
from utils.global_state import update_bluetooth_state, GLOBAL_BLUETOOTH_STATE
# from custom_bt_agent import agent
from utils.pulseaudio_service import remove_loopback_for_device


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


def disconnect_device_dbus(mac: str) -> bool:
    """
    Attempts to disconnect the device with the given MAC from any controller it's connected to.
    Returns True if a disconnect was attempted.
    """
    mac = mac.upper()
    bus = SystemBus()
    manager = bus.get("org.bluez", "/")
    objects = manager.GetManagedObjects()

    attempted = False

    for path, ifaces in objects.items():
        if "org.bluez.Device1" in ifaces:
            dev = ifaces["org.bluez.Device1"]
            dev_mac = dev.get("Address", "").upper()

            if dev_mac == mac and dev.get("Connected", False):
                try:
                    log(f"Calling Disconnect() on {mac}")
                    device = bus.get("org.bluez", path)
                    device.Disconnect()
                    attempted = True
                    remove_loopback_for_device(mac)
                    log(f"Disconnected {mac}")
                except Exception as e:
                    log(f"Failed to disconnect {mac}: {e}")

    if not attempted:
        log(f"No active connection found for {mac}")
    return attempted




def api_disconnect():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    required_fields = ["configID", "configName", "speakers", "settings"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    speakers = data["speakers"]  # format: { mac: name }

    results = {}

    # Refresh the global state first so we're working with accurate data
    update_bluetooth_state()

    for mac, name in speakers.items():
        mac = mac.upper()
        log(f"❌ Marking {mac} as not expected")
        agent.expected_devices.discard(mac)

        log(f"🔌 Attempting direct disconnect of {mac}")
        from custom_bt_agent import disconnect_device_dbus 
        success = disconnect_device_dbus(mac)

        results[mac] = {
            "name": name,
            "disconnected": success
        }

    return jsonify({
        "message": "Speakers unmarked as expected and disconnected.",
        "results": results
    })