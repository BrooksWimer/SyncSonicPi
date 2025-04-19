# global_state.py

import time
from typing import Dict, Any
from .logging import log, RED
from pydbus import SystemBus
from flask import Flask, jsonify, request 
# The master in-memory snapshot. Structure is up to you:
# controllers: { <controllerMAC>: { "hci": "hci0", "status": "UP", "paired": [...], "connected": [...] } }
GLOBAL_BLUETOOTH_STATE: Dict[str, Any] = {
    "controllers": {},   # Key = controller MAC, value = details
    "loopbacks": {}      # track last time we updated
}
# Global template for constructing a device object path from an adapter and a MAC address.
# {adapter} should be something like "hci0", and {mac} is the device's MAC with colons replaced by underscores.
DEVICE_OBJECT_PATH_TEMPLATE = "/org/bluez/{adapter}/dev_{mac}"

def update_bluetooth_state():
    """
    Re-scans the system using D-Bus and updates GLOBAL_BLUETOOTH_STATE with:
    - All known controllers (adapters), including hci name, status, discoverable/pairable/name.
    - All known devices per controller, including full metadata.
    """
    from pydbus import SystemBus
    bus = SystemBus()
    manager = bus.get("org.bluez", "/")
    objects = manager.GetManagedObjects()

    GLOBAL_BLUETOOTH_STATE["controllers"] = {}
    adapter_path_to_mac = {}

    for path, interfaces in objects.items():
        # ---- Adapter (Controller) ----
        if "org.bluez.Adapter1" in interfaces:
            adapter = interfaces["org.bluez.Adapter1"]
            adapter_mac = adapter.get("Address", "").upper()
            hci_name = path.split("/")[-1]

            adapter_path_to_mac[path] = adapter_mac

            GLOBAL_BLUETOOTH_STATE["controllers"][adapter_mac] = {
                "hci": hci_name,
                "status": "UP" if adapter.get("Powered", False) else "DOWN",
                "name": adapter.get("Name", ""),
                "pairable": adapter.get("Pairable", False),
                "discoverable": adapter.get("Discoverable", False),
                "paired": [],
                "connected": [],
                "devices": {}
            }

        # ---- Device (Speaker) ----
        elif "org.bluez.Device1" in interfaces:
            device = interfaces["org.bluez.Device1"]
            dev_mac = device.get("Address", "").upper()
            adapter_path = device.get("Adapter", "")
            adapter_mac = adapter_path_to_mac.get(adapter_path)

            if not adapter_mac or adapter_mac not in GLOBAL_BLUETOOTH_STATE["controllers"]:
                log(f"⚠️ Could not link device {dev_mac} to controller {adapter_path}")
                continue

            ctrl = GLOBAL_BLUETOOTH_STATE["controllers"][adapter_mac]

            if device.get("Paired", False):
                ctrl["paired"].append(dev_mac)
            if device.get("Connected", False):
                ctrl["connected"].append(dev_mac)

            ctrl["devices"][dev_mac] = {
                "adapter": ctrl["hci"],
                "alias": device.get("Alias", ""),
                "name": device.get("Name", ""),
                "connected": device.get("Connected", False),
                "paired": device.get("Paired", False),
                "trusted": device.get("Trusted", False),
                "blocked": device.get("Blocked", False),
                "bonded": device.get("Bonded", False),
                "services_resolved": device.get("ServicesResolved", False),
                "legacy_pairing": device.get("LegacyPairing", False),
                "icon": device.get("Icon", ""),
                "address_type": device.get("AddressType", ""),
                "uuids": device.get("UUIDs", []),
                "class": device.get("Class", 0),
                "modalias": device.get("Modalias", "")
            }
    # fallback in case something was missed
    for path, ifaces in objects.items():
        if "org.bluez.MediaTransport1" in ifaces:
            transport = ifaces["org.bluez.MediaTransport1"]
            dev_path = transport.get("Device", "")
            if dev_path:
                mac_fragment = dev_path.split("/")[-1].replace("dev_", "").replace("_", ":")
                controller_fragment = dev_path.split("/")[3]  # e.g. "hci1"

                # Map hci1 to actual MAC
                for ctrl_mac, ctrl_data in GLOBAL_BLUETOOTH_STATE["controllers"].items():
                    if ctrl_data["hci"] == controller_fragment:
                        if mac_fragment not in ctrl_data["connected"]:
                            log(f"🧠 Inferred {mac_fragment} connected via {ctrl_mac} from MediaTransport1")
                            ctrl_data["connected"].append(mac_fragment)

    log("✅ Global Bluetooth state updated.")



def get_all_controllers() -> list:
    """
    Returns a list of all controller MAC addresses from the global state.
    """
    return list(GLOBAL_BLUETOOTH_STATE.get("controllers", {}).keys())

def get_hci_name_for_adapter(adapter_mac: str) -> str:
    """
    Returns an hci name for the given adapter MAC.
    This is a stub; you can implement a more robust method if needed.
    """
    adapter_mac = adapter_mac.upper()
    controllers = GLOBAL_BLUETOOTH_STATE.get("controllers", {})
    if adapter_mac in controllers:
        return controllers[adapter_mac].get("hci", None)
    else:
        # You may choose to return None or raise an error if the adapter isn't found.
        # Here we return a default value for safety.
        return None

def get_managed_objects():
    """
    Instead of querying D-Bus every time, this function returns the cached controllers.
    (Note: 'bus' parameter is now ignored.)
    """
    log("Using cached managed objects from global state.")
    return GLOBAL_BLUETOOTH_STATE.get("controllers", {})

def get_adapter_by_mac_address(adapter_address):
    """
    Returns details of an adapter from the cached global state for the given address.
    Since update_bluetooth_state() caches adapter info keyed by MAC, we simply lookup.
    The original return format (path and D-Bus object) is no longer available.
    Returns the cached dictionary for the adapter, or None if not found.
    """
    adapter = GLOBAL_BLUETOOTH_STATE.get("controllers", {}).get(adapter_address.upper())
    if adapter:
        log(f"✅ Found adapter in global state for address {adapter_address}")
        return adapter
    else:
        log(f"❌ Adapter {adapter_address} not found in global state")
        return None

def get_device_by_address(adapter_address: str, device_address: str) -> dict:
    """
    Checks the cached global state for the specified adapter (by MAC) and device (by MAC).
    Returns a dictionary with the device's status:
        {
            "found": True/False,
            "paired": True/False,
            "connected": True/False
        }
    If the adapter isn't in the global state, it returns all flags as False.
    """
    adapter_address = adapter_address.upper()
    device_address = device_address.upper()
    
    controllers = GLOBAL_BLUETOOTH_STATE.get("controllers", {})
    adapter_info = controllers.get(adapter_address)
    
    if adapter_info is None:
        log(f"❌ Adapter {adapter_address} not found in global state.")
        return {"found": False, "paired": False, "connected": False}
    
    # Check in the cached lists of paired and connected devices:
    paired_list = [m.upper() for m in adapter_info.get("paired", [])]
    connected_list = [m.upper() for m in adapter_info.get("connected", [])]
    
    is_paired = device_address in paired_list
    is_connected = device_address in connected_list
    found = is_paired or is_connected

    if not found:
        log(f"❌ Device {device_address} not found under adapter {adapter_address} in global state.")
    else:
        log(f"✅ Device {device_address} under adapter {adapter_address} status: paired: {is_paired}, connected: {is_connected}")
    
    return {"found": found, "paired": is_paired, "connected": is_connected}

def build_device_object_path(adapter: str, mac: str) -> str:
    """
    Constructs the D-Bus object path for a Bluetooth device given its adapter (e.g., "hci0")
    and its MAC address. The MAC address is converted to uppercase and colons are replaced with underscores.
    
    Example:
        adapter: "hci0"
        mac: "ac:df:a1:52:8a:41"
        -> returns: "/org/bluez/hci0/dev_AC_DF_A1_52_8A_41"
    """
    normalized_mac = mac.strip().upper().replace(":", "_")
    return DEVICE_OBJECT_PATH_TEMPLATE.format(adapter=adapter, mac=normalized_mac)



def get_mac_for_adapter(adapter: str) -> str:
    """
    Returns the MAC address for a given adapter (e.g., "hci0") by querying the cached global state.
    It iterates over GLOBAL_BLUETOOTH_STATE["controllers"] and returns the MAC for the controller whose
    "hci" property matches the adapter argument. If no matching controller is found, returns None.
    """
    adapter = adapter.strip().lower()
    controllers = GLOBAL_BLUETOOTH_STATE.get("controllers", {})
    for mac, details in controllers.items():
        if details.get("hci", "").lower() == adapter:
            return mac  # the key in the state is the MAC address
    return None

def register_loopback(mac: str, sink_name: str):
    mac = mac.upper()
    GLOBAL_BLUETOOTH_STATE["loopbacks"][mac] = sink_name
    log(f"🔁 Registered loopback: {mac} → {sink_name}")

def remove_device_from_memory(bus, controller_mac: str, device_mac: str):
    adapter_path = f"/org/bluez/{get_hci_name_for_adapter(controller_mac)}"
    device_path = f"{adapter_path}/dev_{device_mac.replace(':', '_')}"
    try:
        adapter = bus.get("org.bluez", adapter_path)
        adapter.RemoveDevice(device_path)
        log(f"🧹 Removed {device_mac} from BlueZ memory at {device_path}")
    except Exception as e:
        log(f"⚠️ Failed to remove {device_mac} from memory: {e}")

def api_get_connected_devices():
    update_bluetooth_state()
    connected_macs = []

    for ctrl_info in GLOBAL_BLUETOOTH_STATE["controllers"].values():
        connected_macs.extend(ctrl_info.get("connected", []))

    return jsonify({"connected": connected_macs})