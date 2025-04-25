import time
import threading
import subprocess
from utils.global_state import update_bluetooth_state, GLOBAL_BLUETOOTH_STATE
from utils.pulseaudio_service import create_loopback
from utils.logging import log
from utils.pulseaudio_service import remove_loopback_for_device
# from endpoints.disconnect import disconnect_device_dbus
import json
from flask import request, jsonify
from utils.pulseaudio_service import setup_pulseaudio
from device_event_watcher import DeviceEventWatcher
from utils.global_state import get_hci_name_for_adapter 
from bus_manager import get_bus

def get_managed_objects(bus):
    return bus.get("org.bluez", "/").GetManagedObjects()

class ConnectionAgent:
    def __init__(self): 
        bus = get_bus()
        self.update_objects()
        self.expected_devices = set()
        self.loopbacks_created = set()
        self.scan_lock = threading.Lock()
        self.scan_cooldown_sec = 10
        self.last_scan_time = 0

    def update_objects(self):
        self.objects = get_managed_objects(self.bus)

    def set_expected(self, macs: list[str], replace: bool = False):
        if replace:
            self.expected_devices = set(macs)
        else:
            self.expected_devices.update(macs)

        log(f"Updated expected devices: {self.expected_devices}")
        self.update_objects()


        for mac in macs:
            status, ctrl_mac, disconnect_list = connect_one_plan(mac, list(self.expected_devices), self.objects)

            for dev_mac, dc_ctrl_mac in disconnect_list:
                log(f"🔻 Disconnecting unexpected device {dev_mac} from {dc_ctrl_mac}")
                device_path = self.get_device_path(dc_ctrl_mac, dev_mac)
                disconnect_device_dbus(device_path, dev_mac, self.bus)

            if ctrl_mac:
                log(f"⚙️ Launching try_reconnect for {mac} on {ctrl_mac}")
                self.try_reconnect(ctrl_mac, mac)

    def start(self):
        if self.running:
            log("Agent is already running.")
            return
        self.running = True
        log("Custom connection agent started.")

    def stop(self):
        self.running = False
        log("Custom connection agent stopped.")

    def ensure_connected_loopback(self, mac: str):
        if mac not in self.expected_devices:
            return
        if mac in self.loopbacks_created:
            return
        sink = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
        if create_loopback(sink):
            self.loopbacks_created.add(mac)
            log(f"✅ Loopback created for connected device {mac}")

    def cleanup_disconnected_device(self, mac: str):
        if mac in self.loopbacks_created:
            remove_loopback_for_device(mac)
            self.loopbacks_created.discard(mac)
            log(f"🧹 Removed loopback for {mac} after disconnection")

    def analyze_device(self, ctrl_mac, dev_mac):
        device_path = self.get_device_path(ctrl_mac, dev_mac)
        device_data = self.objects.get(device_path, {}).get("org.bluez.Device1")
        if not device_data:
            return "run discovery"

        paired = device_data.get("Paired", False)
        trusted = device_data.get("Trusted", False)
        connected = device_data.get("Connected", False)
        uuids = device_data.get("UUIDs", [])

        audio_profile = any("110b" in uuid.lower() for uuid in uuids)

        if not paired:
            return "pair_and_connect"
        if not trusted:
            return "trust_and_connect"
        if not audio_profile:
            return "run discovery"
        if not connected:
            return "connect_only"

        return "already_connected"

    def try_reconnect(self, ctrl_mac, dev_mac):
        state = self.analyze_device(ctrl_mac, dev_mac)
        log(f"Initial reconnect strategy for {dev_mac}: {state}")

        loopback_sink = f"bluez_sink.{dev_mac.replace(':', '_')}.a2dp_sink"
        latency = 100  # TODO: fetch real latency per device
        success = False
        retry_limit = 3

        device_path = self.get_device_path(ctrl_mac, dev_mac)

        for attempt in range(retry_limit):
            log(f"Attempt {attempt+1}/3 — Current state: {state}")

            if state == "already_connected":
                success = True
                break

            elif state == "connect_only":
                if connect_device_dbus(device_path, self.bus):
                    success = True
                    break
                else:
                    log(f"❌ connect_only failed for {dev_mac}")
                    state = "pair_and_connect"

            elif state == "trust_and_connect":
                trust_device_dbus(device_path, self.bus)
                state = "connect_only"

            elif state == "pair_and_connect":
                if pair_device_dbus(device_path, self.bus):
                    state = "trust_and_connect"
                else:
                    log(f"⚠️ Pair failed — removing device and retrying scan")
                    state = "run discovery"

            elif state == "run discovery":
                remove_device_dbus(device_path, self.bus)
                if scan_for_device_dbus(self, ctrl_mac, dev_mac):
                    state = "pair_and_connect"
                else:
                    log(f"❌ Discovery failed for {dev_mac} — giving up")
                    break
   

        if success:
            if create_loopback(loopback_sink, latency):
                log(f"✅ Loopback created for {dev_mac} → {loopback_sink}")
                self.loopbacks_created.add(dev_mac)
            else:
                log(f"⚠️ Connected but loopback creation failed for {dev_mac}")
        else:
            log(f"❌ Final failure — could not reconnect {dev_mac}")


    
    def get_device_path(self, ctrl_mac: str, dev_mac: str) -> str | None:
        dev_mac_fmt = dev_mac.upper().replace(":", "_")
        for path, ifaces in self.objects.items():
            if "org.bluez.Adapter1" in ifaces:
                addr = ifaces["org.bluez.Adapter1"].get("Address", "").upper()
                if addr == ctrl_mac.upper():
                    return f"{path}/dev_{dev_mac_fmt}"
        return None






agent = ConnectionAgent()
watcher = DeviceEventWatcher(agent, agent.bus)



    
def get_adapter_path_from_device(device_path: str) -> str:
    return "/".join(device_path.split("/")[:4])




def scan_for_device_dbus(agent, ctrl_mac: str, target_mac: str, timeout: int = 20) -> str | None:
    """
    Starts discovery on the specified adapter and waits until the target device is found.
    Returns the D-Bus path if found, or None.
    """
    with agent.scan_lock:
        now = time.time()
        if now - agent.last_scan_time < agent.scan_cooldown_sec:
            log(f"Scan for {target_mac} skipped — last run {now - agent.last_scan_time:.1f}s ago.")
            return None
        agent.last_scan_time = now

        ctrl_mac = ctrl_mac.upper()
        target_mac = target_mac.upper()

        # Find the adapter path using agent's object tree
        adapter_path = None
        for path, ifaces in agent.objects.items():
            if "org.bluez.Adapter1" in ifaces:
                addr = ifaces["org.bluez.Adapter1"].get("Address", "").upper()
                if addr == ctrl_mac:
                    adapter_path = path
                    break

        if not adapter_path:
            log(f"Controller {ctrl_mac} not found in managed objects.")
            return None

        try:
            bus = agent.bus
            adapter = bus.get("org.bluez", adapter_path)
            manager = bus.get("org.bluez", "/")
            log(f"Starting scan for {target_mac} on adapter {ctrl_mac} ({adapter_path})")

            try:
                adapter.StopDiscovery()
                time.sleep(1)
            except Exception as e:
                if "InProgress" in str(e):
                    log("Discovery already running — continuing.")
                else:
                    log(f"StopDiscovery failed: {e}")

            try:
                adapter.StartDiscovery()
            except Exception as e:
                if "InProgress" in str(e):
                    log("StartDiscovery already running — continuing anyway.")
                else:
                    log(f"StartDiscovery failed: {e}")
                    return None

            start_time = time.time()
            while time.time() - start_time < timeout:
                agent.update_objects()
                for path, ifaces in agent.objects.items():
                    dev = ifaces.get("org.bluez.Device1")
                    if dev and dev.get("Address", "").upper() == target_mac:
                        if not path.startswith(adapter_path):
                            log(f"Found {target_mac} but on wrong controller: {path}")
                            continue
                        log(f"Found {target_mac} at {path}")
                        try:
                            adapter.StopDiscovery()
                        except Exception as e:
                            log(f"Failed to stop discovery after success: {e}")
                        return path
                time.sleep(1)

            try:
                adapter.StopDiscovery()
            except Exception as e:
                log(f"Timed out and failed to stop discovery: {e}")
            log(f"Timed out — {target_mac} not found.")
            return None

        except Exception as e:
            log(f"scan_for_device_dbus failed for {target_mac} on {ctrl_mac}: {e}")
            return None









def connect_device_dbus(device_path: str, bus) -> bool:
    try:
        device = bus.get("org.bluez", device_path)
        log(f"Connecting to device at {device_path}")
        device.Connect()
        return True
    except Exception as e:
        log(f"Failed to connect at {device_path}: {e}")
        return False


def trust_device_dbus(device_path: str, bus) -> bool:
    try:
        device = bus.get("org.bluez", device_path)
        log(f"Setting Trusted=true for device at {device_path}")
        device.Trusted = True
        return True
    except Exception as e:
        log(f"Failed to trust device at {device_path}: {e}")
        return False


def pair_device_dbus(device_path: str, bus) -> bool:
    try:
        time.sleep(1.5)
        device = bus.get("org.bluez", device_path)
        log(f"Pairing device at {device_path}")
        device.Pair()
        return True
    except Exception as e:
        log(f"Failed to pair device at {device_path}: {e}")
        return False


def remove_device_dbus(device_path: str, bus) -> bool:
    adapter_path = get_adapter_path_from_device(device_path)
    try:
        adapter = bus.get("org.bluez", adapter_path)
        log(f"Removing device at {device_path} from adapter {adapter_path}")
        adapter.RemoveDevice(device_path)
        return True
    except Exception as e:
        log(f"Failed to remove device at {device_path}: {e}")
        return False



def disconnect_device_dbus(device_path: str, mac: str, bus) -> bool:
    """
    Disconnects the specified Bluetooth device using its full D-Bus path.
    """
    try:
        device = bus.get("org.bluez", device_path)
        log(f"Attempting disconnect of {mac} at {device_path}")
        device.Disconnect()
        remove_loopback_for_device(mac)
        log(f"Successfully disconnected {mac} at {device_path}")
        return True
    except Exception as e:
        log(f"Failed to disconnect {mac} at {device_path}: {e}")
        return False
    

def disconnect_all_instances(mac: str, objects: dict, bus) -> bool:
    """
    Disconnects the given device from all controllers where it is currently connected.
    Uses the full D-Bus object tree instead of any global state.
    """
    mac = mac.upper()
    mac_fmt = mac.replace(":", "_")
    attempted = False

    for path, ifaces in objects.items():
        if "org.bluez.Device1" in ifaces:
            dev = ifaces["org.bluez.Device1"]
            address = dev.get("Address", "").upper()
            connected = dev.get("Connected", False)
            if address == mac and connected:
                try:
                    device = bus.get("org.bluez", path)
                    log(f"Attempting to disconnect {mac} at {path}")
                    device.Disconnect()
                    remove_loopback_for_device(mac)
                    log(f"Successfully disconnected {mac} at {path}")
                    attempted = True
                except Exception as e:
                    log(f"Failed to disconnect {mac} at {path}: {e}")

    if not attempted:
        log(f"No active connections found for {mac} in managed objects")
    return attempted



def connect_one_plan(target_mac: str, allowed_macs: list[str], objects: dict) -> tuple[str, str, list[tuple[str, str]]]:
    """
    Determines the appropriate connection plan for a given target device:
    - If already connected correctly, returns 'already_connected'.
    - If needs connection and a controller is available, returns 'needs_connection'.
    - If no suitable controllers are available, returns 'error'.

    Args:
        target_mac (str): The MAC address of the target device.
        allowed_macs (list[str]): The list of allowed speaker MACs.
        objects (dict): The D-Bus object tree from GetManagedObjects().

    Returns:
        tuple[str, str, list[tuple[str, str]]]:
            - Status string ('already_connected', 'needs_connection', or 'error')
            - Controller MAC address to use (if applicable)
            - List of (device_mac, controller_mac) tuples to disconnect
    """
    target_mac = target_mac.upper()
    allowed_macs = [mac.upper() for mac in allowed_macs]
    disconnect_list = []
    target_connected_on = []
    config_speaker_usage = {}
    used_controllers = set()
    adapters = {}

    # Build a map of adapter MACs to their object paths
    for path, ifaces in objects.items():
        if "org.bluez.Adapter1" in ifaces:
            addr = ifaces["org.bluez.Adapter1"].get("Address", "").upper()
            hci_name = path.split("/")[-1]
            if hci_name == "hci0":
                continue  # Skip reserved adapter
            adapters[addr] = path

    log(f"Planning connection for target: {target_mac}")
    log(f"Allowed MACs in config: {allowed_macs}")

    # Analyze all devices
    for path, ifaces in objects.items():
        dev = ifaces.get("org.bluez.Device1")
        if not dev:
            continue
        dev_mac = dev.get("Address", "").upper()
        adapter_prefix = "/".join(path.split("/")[:4])

        ctrl_mac = None
        for mac, adapter_path in adapters.items():
            if adapter_prefix == adapter_path:
                ctrl_mac = mac
                break

        if not ctrl_mac:
            continue  # This device does not belong to a recognized adapter

        if dev.get("Connected", False):
            log(f"Found connected device: {dev_mac} on {ctrl_mac}")

            if dev_mac in allowed_macs:
                config_speaker_usage.setdefault(dev_mac, []).append(ctrl_mac)

            if dev_mac == target_mac:
                target_connected_on.append(ctrl_mac)
                log(f"Target {dev_mac} already connected on {ctrl_mac}")

            elif dev_mac not in allowed_macs:
                disconnect_list.append((dev_mac, ctrl_mac))
                log(f"Out-of-config device {dev_mac} → marked for disconnection")

            elif dev_mac in allowed_macs:
                used_controllers.add(ctrl_mac)
                log(f"Config speaker {dev_mac} occupies controller {ctrl_mac}")

    log(f"Target is currently connected on: {target_connected_on}")
    log(f"Disconnect list built: {disconnect_list}")
    log(f"Controllers in use by config devices: {used_controllers}")

    # Handle multiple connections of target
    if len(target_connected_on) > 1:
        controller_to_keep = target_connected_on[0]
        for ctrl_mac in target_connected_on[1:]:
            disconnect_list.append((target_mac, ctrl_mac))
        log(f"Target connected on multiple controllers, keeping {controller_to_keep}, disconnecting others")
        return "already_connected", controller_to_keep, disconnect_list

    # Target connected once: ensure it's not sharing with another config speaker
    if len(target_connected_on) == 1:
        controller = target_connected_on[0]
        for mac, controllers in config_speaker_usage.items():
            if mac != target_mac and controller in controllers:
                disconnect_list.append((target_mac, controller))
                log(f"Target {target_mac} shares controller {controller} with config speaker {mac}, reallocating")

                # Try to find a free controller
                for new_ctrl_mac in adapters:
                    if new_ctrl_mac not in used_controllers and new_ctrl_mac != controller:
                        log(f"Assigning free controller {new_ctrl_mac} to target {target_mac}")
                        return "needs_connection", new_ctrl_mac, disconnect_list

                # Fallback: free a duplicate
                for mac2, controllers2 in config_speaker_usage.items():
                    if len(controllers2) > 1:
                        ctrl_to_free = controllers2[1]
                        disconnect_list.append((mac2, ctrl_to_free))
                        log(f"Freeing {ctrl_to_free} from {mac2} to connect target {target_mac}")
                        return "needs_connection", ctrl_to_free, disconnect_list

                log(f"No controller available after rebalance for target {target_mac}")
                return "error", "", disconnect_list

        return "already_connected", controller, disconnect_list

    # Target is not currently connected anywhere
    for ctrl_mac in adapters:
        if ctrl_mac not in used_controllers:
            log(f"Free controller {ctrl_mac} found for target {target_mac}")
            return "needs_connection", ctrl_mac, disconnect_list

    for mac, controllers in config_speaker_usage.items():
        if len(controllers) > 1:
            ctrl_to_free = controllers[1]
            disconnect_list.append((mac, ctrl_to_free))
            log(f"Freeing controller {ctrl_to_free} from {mac} to connect target {target_mac}")
            return "needs_connection", ctrl_to_free, disconnect_list

    log(f"No available controller found for target {target_mac}")
    return "error", "", disconnect_list









def api_connect_one():
    """
    Accepts a single target speaker MAC and marks it as expected.
    The connection agent handles reconnection logic.
    """

    try:
        log("🔄 Resetting Bluetooth adapters...")
        subprocess.run(["/home/syncsonic2/reset_bt_adapters.sh"], check=True)
        log("✅ Bluetooth adapters reset successfully.")
    except subprocess.CalledProcessError as e:
        log(f"❌ Failed to reset Bluetooth adapters: {str(e)}")
        return jsonify({"error": f"Reset script failed: {str(e)}"}), 500
    
    data = request.get_json()
    if not data or "targetSpeaker" not in data or "settings" not in data:
        return jsonify({"error": "Missing 'targetSpeaker' or 'settings'"}), 400

    target = data["targetSpeaker"]
    if "mac" not in target or "name" not in target:
        return jsonify({"error": "targetSpeaker missing 'mac' or 'name'"}), 400
   

    mac = target["mac"].upper()
    name = target["name"]
    settings = data["settings"]

    log("---- /connect-one ----")
    log(f"Target Speaker: {mac} / {name}")
    log(f"Speaker Settings: {settings}")

    # Setup PulseAudio once
    setup_pulseaudio()

    # Pass expected MAC to the agent and trigger immediate reconnect attempt
    agent.set_expected([mac], replace=False)

    return jsonify({"success": True, "message": f"Target {name} marked as expected. Agent will handle connection."})


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

    # Refresh internal D-Bus object state
    agent.update_objects()

    for mac, name in speakers.items():
        mac = mac.upper()
        log(f"Marking {mac} as not expected")
        agent.expected_devices.discard(mac)

        log(f"Attempting to disconnect all instances of {mac}")
        success = disconnect_all_instances(mac, agent.objects, agent.bus)

        results[mac] = {
            "name": name,
            "disconnected": success
        }

    return jsonify({
        "message": "Speakers unmarked as expected and disconnected.",
        "results": results
    })















