from pydbus import SystemBus
import time
from .logging import log, RED
from utils.logging import log
import subprocess
from gi.repository import GLib
import glob
import os
import json
import multiprocessing

def wait_for_property(bus, obj_path, interface, prop, target_value, timeout=10):
    log(f"🔍 Waiting for property {prop} on {obj_path} to become {target_value}")
    loop = GLib.MainLoop()
    matched = False

    def on_props_changed(iface, changed, invalidated, *args):
        nonlocal matched
        log(f"📱 Property change detected on {obj_path}:")
        log(f"  Interface: {iface}")
        log(f"  Changed: {changed}")
        log(f"  Invalidated: {invalidated}")
        if prop in changed:
            log(f"  {prop} changed to {changed[prop]}")
            if changed[prop] == target_value:
                log(f"✅ Target value {target_value} matched!")
                matched = True
                loop.quit()

    log(f"📱 Subscribing to property changes on {obj_path}")
    bus.subscribe(
        iface="org.freedesktop.DBus.Properties",
        signal="PropertiesChanged",
        object=obj_path,
        signal_fired=on_props_changed,
    )

    log(f"⏱️ Setting timeout for {timeout} seconds")
    GLib.timeout_add_seconds(timeout, loop.quit)
    log("🔄 Starting main loop to wait for property change")
    loop.run()
    log(f"🏋️ Main loop ended. Property matched: {matched}")
    return matched

def build_connection_gameplan(devices, controllers, nested_paired, nested_connected):
    log("🎮 Building connection gameplan")
    log(f"📱 Devices to connect: {devices}")
    log(f"🎮 Available controllers: {controllers}")
    log(f"🤝 Currently paired: {nested_paired}")
    log(f"🔌 Currently connected: {nested_connected}")

    assigned_controllers = set()
    gameplan = {}

    # Build quick lookup for currently connected and paired status
    currently_connected = {}
    currently_paired = {}

    for key in nested_connected:
        ctrl, mac = key.split("|")
        log(f"🔌 Found connected device: {mac} on controller {ctrl}")
        currently_connected.setdefault(mac.upper(), []).append(ctrl)

    for key in nested_paired:
        ctrl, mac = key.split("|")
        log(f"🤝 Found paired device: {mac} on controller {ctrl}")
        currently_paired.setdefault(mac.upper(), []).append(ctrl)

    for mac, name in devices.items():
        mac_upper = mac.upper()
        log(f"\n📱 Processing device: {name} ({mac_upper})")
        speaker_plan = {
            "name": name,
            "assigned_controller": None,
            "action": None,
            "disconnect": []
        }

        connected_ctrls = currently_connected.get(mac_upper, [])
        log(f"🔍 Currently connected to controllers: {connected_ctrls}")

        # New check: only keep an existing connection if its controller is not already assigned
        if len(connected_ctrls) == 1 and connected_ctrls[0] not in assigned_controllers:
            ctrl = connected_ctrls[0]
            log(f"✅ Keeping existing connection on controller {ctrl}")
            speaker_plan["assigned_controller"] = ctrl
            speaker_plan["action"] = "none"
            assigned_controllers.add(ctrl)
        elif len(connected_ctrls) > 0:
            # Try to find an unassigned connected controller.
            found = False
            for ctrl in connected_ctrls:
                if ctrl not in assigned_controllers:
                    log(f"✅ Keeping available connected controller {ctrl}, disconnecting other connections")
                    speaker_plan["assigned_controller"] = ctrl
                    speaker_plan["action"] = "none"
                    assigned_controllers.add(ctrl)
                    found = True
                    break
            if not found:
                # Fall through if all connected controllers are already assigned.
                log("🔍 All connected controllers are already assigned; will check paired controllers.")
        
        if speaker_plan["assigned_controller"] is None:
            # Device is not connected (or no available connected controller) -> try paired controllers
            paired_ctrls = currently_paired.get(mac_upper, [])
            log(f"🔍 Currently paired to controllers: {paired_ctrls}")
            selected = False
            for ctrl in paired_ctrls:
                if ctrl not in assigned_controllers:
                    log(f"✅ Will connect to paired controller {ctrl}")
                    speaker_plan["assigned_controller"] = ctrl
                    speaker_plan["action"] = "pair_and_connect"
                    assigned_controllers.add(ctrl)
                    selected = True
                    break

            if not selected:
                log("🔍 Looking for available controller for new pairing")
                for ctrl in controllers:
                    if ctrl not in assigned_controllers:
                        log(f"✅ Will pair and connect to new controller {ctrl}")
                        speaker_plan["assigned_controller"] = ctrl
                        speaker_plan["action"] = "pair_and_connect"
                        assigned_controllers.add(ctrl)
                        selected = True
                        break

            if not selected:
                log("❌ No available controller found")
                speaker_plan["action"] = "error_no_available_controller"

        gameplan[mac] = speaker_plan
        log(f"📋 Final plan for {name}: {speaker_plan}")
    
    # Force disconnect anything connected to a reserved controller, if needed
    reserved_controller = "B8:27:EB:07:4B:98"
    log("\n🎮 Final gameplan:")
    for mac, plan in gameplan.items():
        if reserved_controller in currently_connected.get(mac.upper(), []):
            if plan["assigned_controller"] == reserved_controller:
                log(f"🔒 Forcing disconnect of {mac} from reserved controller {reserved_controller}")
                plan["disconnect"].append(reserved_controller)
        log(f"  {mac}: {plan}")
    return gameplan


def get_managed_objects(bus):
    log("🔍 Getting managed objects from D-Bus")
    manager = bus.get("org.bluez", "/")
    objects = manager.GetManagedObjects()
    log(f"📦 Found {len(objects)} managed objects")
    return objects

def get_adapter_by_address(bus, adapter_address, objects):
    log(f"🔍 Looking for adapter with address {adapter_address}")
    for path, ifaces in objects.items():
        adapter = ifaces.get("org.bluez.Adapter1")
        if adapter and adapter.get("Address", "").upper() == adapter_address.upper():
            log(f"✅ Found adapter at {path}")
            return path, bus.get("org.bluez", path)
    log(f"❌ Adapter {adapter_address} not found")
    return None, None

def get_device_by_address(bus, adapter_path, device_address, objects):
    log(f"🔍 Looking for device {device_address} under adapter {adapter_path}")
    for path, ifaces in objects.items():
        if not path.startswith(adapter_path):
            continue
        device = ifaces.get("org.bluez.Device1")
        if device and device.get("Address", "").upper() == device_address.upper():
            log(f"✅ Found device at {path}")
            return path, bus.get("org.bluez", path)
    log(f"❌ Device {device_address} not found under adapter {adapter_path}")
    return None, None

def get_connected_device_path(bus, device_address, objects):
    log(f"🔍 Searching for connected instance of device {device_address}")
    for path, ifaces in objects.items():
        device = ifaces.get("org.bluez.Device1")
        if not device:
            continue
        if device.get("Address", "").upper() == device_address.upper():
            connected = device.get("Connected", False)
            if connected:
                log(f"✅ Found connected device at {path}")
                return path, bus.get("org.bluez", path)
            else:
                log(f"⚠️ Device found at {path}, but not connected")
    log(f"❌ No connected instance of device {device_address} found")
    return None, None

def disconnect_device(bus, device_address, objects=None):
    if objects is None:
        objects = get_managed_objects(bus)

    path, device_obj = get_connected_device_path(bus, device_address, objects)
    if path is None:
        log(f"❌ Could not find connected device {device_address} to disconnect")
        return False

    try:
        log(f"🔌 Disconnecting device at {path}")
        device_obj.Disconnect()
        log(f"✅ Disconnect command sent to {device_address}")
        return True
    except Exception as e:
        log(f"❌ Failed to disconnect {device_address}: {e}")
        return False


def _pair_device(device_obj, return_dict):
    try:
        device_obj.Pair()
        return_dict["result"] = "success"
    except Exception as e:
        return_dict["result"] = f"error:{str(e)}"

def pair_with_timeout(device_obj, timeout=10):
    manager = multiprocessing.Manager()
    return_dict = manager.dict()
    process = multiprocessing.Process(target=_pair_device, args=(device_obj, return_dict))

    process.start()
    process.join(timeout)

    if process.is_alive():
        process.terminate()
        process.join()
        return "timeout"

    return return_dict.get("result", "unknown")

def pair_and_connect(bus, device_obj, dev_path, device_addr):
    log(f"🤝 Pairing and connecting {device_addr}")

   # Verify connection
    try:
        if device_obj.Pair():
            log(f"✅ {device_addr} is now Pair")
            return True
        else:
            log(f"❌ {device_addr} is not Pair after Connect()")
    except Exception as e:
        log(e)

    time.sleep(2)

    # Mark as trusted
    try:
        log(f"🔒 Trusting {device_addr}")
        device_obj.Trusted = True
    except Exception as e:
        log(f"⚠️ Couldn't set trusted: {e}")

    time.sleep(2)

    # Try to connect
    try:
        log(f"🔌 Connecting attempt")
        device_obj.Connect()
        time.sleep(2)  # Allow time to reflect status
    except Exception as e:
        log(f"❌ Connection error: {e}")
        return False

    # Verify connection
    try:
        if device_obj.Connected:
            log(f"✅ {device_addr} is now connected")
            return True
        else:
            log(f"❌ {device_addr} is not connected after Connect()")
            return False
    except Exception as e:
        log(f"❌ Could not check connection status: {e}")
        return False


def introspect_paired_and_connected():
    log("🔍 Introspecting paired and connected devices (D-Bus only)")
    nested_paired = {}
    nested_connected = {}

    try:
        bus = SystemBus()
        objects = get_managed_objects(bus)

        if not objects:
            log("❌ No D-Bus objects found")
            return {}, {}

        # Map adapter D-Bus paths to addresses
        adapter_map = {}
        for path, ifaces in objects.items():
            adapter = ifaces.get("org.bluez.Adapter1")
            if adapter and "Address" in adapter:
                adapter_map[path] = adapter["Address"]
                log(f"✅ Found controller: {adapter['Address']} at {path}")

        # Walk through Device1 objects
        for path, ifaces in objects.items():
            device = ifaces.get("org.bluez.Device1")
            if not device:
                continue

            mac = device.get("Address")
            name = device.get("Name", "Unknown")
            paired = device.get("Paired", False)
            connected = device.get("Connected", False)
            adapter_path = device.get("Adapter")

            ctrl_addr = adapter_map.get(adapter_path)
            if not ctrl_addr:
                log(f"⚠️ Could not map adapter path {adapter_path} to controller address")
                continue

            key = f"{ctrl_addr}|{mac}"
            if paired:
                nested_paired[key] = name
                log(f"✅ Found paired device: {name} ({mac}) on {ctrl_addr}")
            if connected:
                nested_connected[key] = name
                log(f"✅ Found connected device: {name} ({mac}) on {ctrl_addr}")

        log(f"📋 Final paired devices: {nested_paired}")
        log(f"📋 Final connected devices: {nested_connected}")
        return nested_paired, nested_connected

    except Exception as e:
        log(f"❌ Error during D-Bus introspection: {e}")
        return {}, {}
    
def is_device_connected(bus, mac, objects=None):
    if objects is None:
        objects = get_managed_objects(bus)

    device_path = None
    for path, interfaces in objects.items():
        if "org.bluez.Device1" in interfaces:
            device = interfaces["org.bluez.Device1"]
            log(f"🔍 Checking device at {path}: {device}")
            log(device.get("Address") == mac)
            if device.get("Address") == mac:
                device_path = path
                break

    if device_path is None:
        return False  # Not found means not connected

    device_interface = bus.get("org.bluez", device_path)
    return device_interface.Connected


def run_connection_plan(gameplan):
    bus = SystemBus()
    
    log("🔄 Step 1: Performing all disconnects first")
    for mac, plan in gameplan.items():
        for ctrl in plan["disconnect"]:
            log(f"🔌 Disconnecting {mac} from {ctrl}")
            disconnect_device(bus, mac)
            time.sleep(0.5)

    max_passes = 3
    for attempt in range(max_passes):
        log(f"\n🔁 Connection Pass {attempt + 1}")
        all_objects = get_managed_objects(bus)
        remaining = []

        for mac, plan in gameplan.items():
            ctrl = plan["assigned_controller"]
            action = plan["action"]
            name = plan["name"]

            if action == "none":
                log(f"✅ Skipping {name} ({mac}) — already connected")
                continue

            adapter_path, _ = get_adapter_by_address(bus, ctrl, all_objects)
            dev_path, device_obj = get_device_by_address(bus, adapter_path, mac, all_objects)

            if not device_obj:
                log(f"🔍 Device {mac} not found on controller {ctrl} — trying discovery")

                try:
                    _, adapter_obj = get_adapter_by_address(bus, ctrl, all_objects)
                    if adapter_obj:
                        adapter_obj.StartDiscovery()
                        time.sleep(5)
                        adapter_obj.StopDiscovery()
                        all_objects = get_managed_objects(bus)
                        dev_path, device_obj = get_device_by_address(bus, adapter_path, mac, all_objects)
                    else:
                        log(f"❌ Could not get adapter object for controller {ctrl}")
                except Exception as e:
                    log(f"❌ Discovery failed: {e}")

                if not device_obj:
                    log(f"❌ Still couldn't find {mac} on controller {ctrl} after discovery")
                    remaining.append(mac)
                    break



            success = pair_and_connect(bus, device_obj, dev_path, mac)
            if success:
                continue

            time.sleep(2)  # short pause before retrying

            if not success:
                log(f"❌ Giving up on {mac} after seconds")
                remaining.append(mac)

            

        if not remaining:
            log("✅ All devices connected successfully!")
            return True
        else:
            log(f"🔁 Devices still not connected: {remaining}")
            time.sleep(2)

    log("❌ Some devices failed to connect after retries")
    return False

def get_mac_for_adapter(adapter: str = "hci0") -> str:
    path = f"/sys/class/bluetooth/{adapter}/address"
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


