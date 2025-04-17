# utils/bluetooth.py
from pydbus import SystemBus
import time
from .logging import log, RED
from utils.logging import log
from utils.bluetooth import get_managed_objects




def wait_for_property(bus, obj_path, interface, prop, target_value, timeout=10):
    loop = GLib.MainLoop()
    matched = False

    def on_props_changed(iface, changed, invalidated):
        nonlocal matched
        if prop in changed:
            log(f"{prop} changed to {changed[prop]}")
            if changed[prop] == target_value:
                matched = True
                loop.quit()

    bus.subscribe(
        iface="org.freedesktop.DBus.Properties",
        signal="PropertiesChanged",
        path=obj_path,
        signal_fired=on_props_changed,
    )

    GLib.timeout_add_seconds(timeout, loop.quit)  # Quit after timeout
    loop.run()

    return matched






def build_connection_gameplan(devices, controllers, nested_paired, nested_connected):
    """
    Build a gameplan dict for how to handle each speaker.

    :param devices: dict of { "MAC": "Speaker Name" }
    :param controllers: list of controller MAC addresses
    :param nested_paired: dict like { "<ctrl>:<mac>": "Name" }
    :param nested_connected: dict like { "<ctrl>:<mac>": "Name" }

    :return: dict with instructions for each speaker
    """
    assigned_controllers = set()
    gameplan = {}

    # Build quick-lookup for currently connected and paired status
    currently_connected = {}
    currently_paired = {}

    for key in nested_connected:
        ctrl, mac = key.split("|")
        currently_connected.setdefault(mac.upper(), []).append(ctrl)

    for key in nested_paired:
        ctrl, mac = key.split("|")
        currently_paired.setdefault(mac.upper(), []).append(ctrl)

    for mac, name in devices.items():
        mac_upper = mac.upper()
        speaker_plan = {
            "name": name,
            "assigned_controller": None,
            "action": None,
            "disconnect": []
        }

        # 1. If already connected, keep the connection if the controller is available
        connected_ctrls = currently_connected.get(mac_upper, [])
        selected = False
        for ctrl in connected_ctrls:
            if ctrl not in assigned_controllers:
                speaker_plan["assigned_controller"] = ctrl
                speaker_plan["action"] = "none"
                assigned_controllers.add(ctrl)
                selected = True
                break

        # 2. If paired on a controller, try connecting to a free paired controller
        if not selected:
            paired_ctrls = currently_paired.get(mac_upper, [])
            for ctrl in paired_ctrls:
                if ctrl not in assigned_controllers:
                    speaker_plan["assigned_controller"] = ctrl
                    speaker_plan["action"] = "connect_only"
                    assigned_controllers.add(ctrl)
                    selected = True
                    break

        # 3. Try pairing to a completely new controller
        if not selected:
            for ctrl in controllers:
                if ctrl not in assigned_controllers:
                    speaker_plan["assigned_controller"] = ctrl
                    speaker_plan["action"] = "pair_and_connect"
                    assigned_controllers.add(ctrl)
                    selected = True
                    break

        # 4. If no available controller
        if not selected:
            speaker_plan["action"] = "error_no_available_controller"

        # 5. Determine if we need to disconnect from any other controllers
        all_connected_ctrls = currently_connected.get(mac_upper, [])
        for ctrl in all_connected_ctrls:
            if ctrl != speaker_plan["assigned_controller"]:
                speaker_plan["disconnect"].append(ctrl)

        gameplan[mac] = speaker_plan

    return gameplan




def get_managed_objects(bus):
    manager = bus.get("org.bluez", "/")
    return manager.GetManagedObjects()

def get_adapter_by_address(bus, adapter_address, objects):
    for path, ifaces in objects.items():
        adapter = ifaces.get("org.bluez.Adapter1")
        if adapter and adapter.get("Address", "").upper() == adapter_address.upper():
            return path, bus.get("org.bluez", path)
    return None, None

def get_device_by_address(bus, adapter_path, device_address, objects):
    for path, ifaces in objects.items():
        if not path.startswith(adapter_path):
            continue
        device = ifaces.get("org.bluez.Device1")
        if device and device.get("Address", "").upper() == device_address.upper():
            return path, bus.get("org.bluez", path)
    return None, None

def disconnect_device(bus, adapter_addr, device_addr):
    objects = get_managed_objects(bus)
    adapter_path, _ = get_adapter_by_address(bus, adapter_addr, objects)

    if not adapter_path:
        log(f"Adapter {adapter_addr} not found.")
        return False

    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)

    if not device_obj:
        log(f"Device {device_addr} not found under adapter {adapter_addr}.")
        # Helpful log: show what's available
        for path, ifaces in objects.items():
            if "org.bluez.Device1" in ifaces:
                addr = ifaces["org.bluez.Device1"].get("Address")
                log(f"Seen device at {path}: {addr}")
        return False

    log(f"Found device {device_addr} at {dev_path}, disconnecting...")
    try:
        device_obj.Disconnect()
        time.sleep(2)
        return True
    except Exception as e:
        log(f"Error disconnecting {device_addr}: {e}")
        return False



def pair_and_connect(bus, adapter_addr, device_addr):
    objects = get_managed_objects(bus)
    adapter_path, adapter_obj = get_adapter_by_address(bus, adapter_addr, objects)

    if not adapter_obj:
        log(f"Adapter {adapter_addr} not found")
        return False

    # Start discovery and wait a bit
    try:
        log(f"Starting discovery on adapter {adapter_addr}...")
        adapter_obj.StartDiscovery()
        time.sleep(5)
        adapter_obj.StopDiscovery()
        time.sleep(1)
    except Exception as e:
        log(f"Discovery error on {adapter_addr}: {e}")

    # Refresh device object after discovery
    objects = get_managed_objects(bus)
    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
    if not device_obj:
        log(f"Device {device_addr} still not found after discovery")
        return False

    try:
        if not device_obj.Paired:
            log(f"Pairing device {device_addr} on {adapter_addr}...")
            device_obj.Pair()
            time.sleep(5)
        else:
            log(f"Device {device_addr} already paired")
    except Exception as e:
        log(f"Pairing error for {device_addr}: {e}")
        return False

    try:
        device_obj.Trusted = True
        log(f"Marked {device_addr} as trusted")
    except Exception as e:
        log(f"Trust error: {e}")

    try:
        log(f"Connecting to {device_addr}...")
        device_obj.Connect()
        time.sleep(3)
    except Exception as e:
        log(f"Connection error: {e}")
        return False

    # Final verification
    objects = get_managed_objects(bus)
    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
    if device_obj and device_obj.Connected:
        log(f"Device {device_addr} successfully connected")
        return True
    else:
        log(f"Device {device_addr} not connected after attempt")
        return False



def connect_only(bus, adapter_addr, device_addr):
    objects = get_managed_objects(bus)
    adapter_path, adapter_obj = get_adapter_by_address(bus, adapter_addr, objects)
    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
    try:
        adapter_obj.StartDiscovery()
        time.sleep(5)
        adapter_obj.StopDiscovery()
        device_obj.Connect()
        time.sleep(3)
        return device_obj.Connected
    except Exception as e:
        log(f"Connect error for {device_addr}: {e}")
        return False





def introspect_paired_and_connected():
    """
    Returns dictionaries of paired and connected devices for each controller.
    Format: { "<ctrl_mac>|<device_mac>": "Device Name" }
    """
    nested_paired = {}
    nested_connected = {}

    try:
        bus = SystemBus()
        objects = get_managed_objects(bus)
        if not objects:
            log("⚠️ No D-Bus objects found. BlueZ might not be running.")
            return {}, {}

        controllers = {}
        for path, ifaces in objects.items():
            adapter = ifaces.get("org.bluez.Adapter1")
            if adapter:
                addr = adapter.get("Address")
                if addr:
                    controllers[path] = addr
                else:
                    log(f"⚠️ Adapter at {path} missing Address field.")

        if not controllers:
            log("❌ No Bluetooth controllers found.")
            return {}, {}

        log(f"✅ Found controllers: {list(controllers.values())}")

        for path, ifaces in objects.items():
            device = ifaces.get("org.bluez.Device1")
            if not device:
                continue

            mac = device.get("Address")
            name = device.get("Name", "Unknown")
            connected = device.get("Connected", False)

            if not mac:
                log(f"⚠️ Device at {path} missing Address. Skipping.")
                continue

            # Attempt to locate the adapter/controller this device belongs to
            adapter_path_parts = path.split("/")
            if len(adapter_path_parts) < 5:
                log(f"⚠️ Unexpected device object path: {path}")
                continue

            adapter_path = "/".join(adapter_path_parts[:5])
            ctrl = controllers.get(adapter_path)
            if not ctrl:
                log(f"⚠️ Couldn't resolve controller for device {mac} at path {path}")
                continue

            key = f"{ctrl}|{mac}"
            nested_paired[key] = name
            if connected:
                nested_connected[key] = name

        log(f"✅ Paired devices: {nested_paired}")
        log(f"✅ Connected devices: {nested_connected}")
        return nested_paired, nested_connected

    except Exception as e:
        log(f"❌ Error during introspection: {e}")
        return {}, {}

