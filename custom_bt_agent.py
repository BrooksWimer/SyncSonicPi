import time
import threading
import subprocess
from pydbus import SystemBus
from utils.global_state import update_bluetooth_state, GLOBAL_BLUETOOTH_STATE
from utils.pulseaudio_service import create_loopback
from utils.logging import log
from utils.pulseaudio_service import remove_loopback_for_device
# from endpoints.disconnect import disconnect_device_dbus
import json
from flask import request, jsonify
from utils.pulseaudio_service import setup_pulseaudio


class ConnectionAgent:
    def __init__(self): 
        self.running = False
        self.bus = SystemBus()
        self.lock = threading.Lock()
        self.expected_devices = set()
        self.loopbacks_created = set()
        self.scan_lock = threading.Lock()
        self.last_scan_time = 0
        self.scan_cooldown_sec = 10


    def set_expected(self, macs: list[str], replace: bool = False):
        if replace:
            self.expected_devices = set(macs)
        else:
            self.expected_devices.update(macs)

        log(f"Updated expected devices: {self.expected_devices}")
        self.check_and_reconnect_all()


    def start(self):
        if self.running:
            log("Agent is already running.")
            return
        self.running = True
        threading.Thread(target=self.run, daemon=True).start()
        log("Custom connection agent started.")

    def stop(self):
        self.running = False
        log("Custom connection agent stopped.")

    def run(self):
        while self.running:
            self.check_and_reconnect_all()
            time.sleep(300)

    
    def check_and_reconnect_all(self):
        update_bluetooth_state()
        log("📡 Controllers snapshot:")
        log(json.dumps(GLOBAL_BLUETOOTH_STATE.get("controllers", {}), indent=2))
        with self.lock:
            for mac in list(self.expected_devices):
                status, controller_mac, disconnect_list = connect_one_plan(mac, list(self.expected_devices))

                for dev_mac, ctrl_mac in disconnect_list:
                    log(f"🔻 Disconnecting unexpected device {dev_mac} from {ctrl_mac}")
                    disconnect_device_dbus(dev_mac)
                    self.loopbacks_created.discard(mac)

                if status == "already_connected" and controller_mac:
                    if mac in self.loopbacks_created:
                        log(f"✅ {mac} already connected and loopback known — skipping.")
                        continue  # Skip this MAC, nothing to do
                    else:
                        log(f"🔍 {mac} connected but no recorded loopback — creating.")
                        sink_prefix = f"bluez_sink.{mac.replace(':', '_')}"
                        if create_loopback(sink_prefix):
                            self.loopbacks_created.add(mac)
                        continue

                # Only reach here if we need reconnect or pairing
                if controller_mac:
                    self.try_reconnect(controller_mac, mac)

    


    def try_reconnect(self, ctrl_mac, dev_mac):
        recommendation = self.analyze_device(ctrl_mac, dev_mac)
        log(f"Reconnect strategy for {dev_mac}: {recommendation}")

        success = False
        if recommendation == "already_connected":
            log(f"{dev_mac} is already connected — ensuring loopback is active.")
            latency = 100  # Fetch this from `settings` if available
            sink_prefix = f"bluez_sink.{dev_mac.replace(':', '_')}"
            if create_loopback(sink_prefix, latency):
                log(f"Loopback ensured for already connected device {dev_mac}")
                log(f"Loopback created for {dev_mac} → {pactl_sink}")
            else:
                log(f"⚠️ Loopback creation failed for already connected device {dev_mac}")
            return
        if recommendation == "connect_only":
            try:
                success = connect_device_dbus(ctrl_mac, dev_mac)
            except Exception as e:
                error_msg = str(e)
                log(f"connect_device_dbus raised exception: {error_msg}")
                if "br-connection-page-timeout" in error_msg:
                    log(f"🔄 Connection timeout for {dev_mac} — retrying pair/trust/connect.")
                    remove_device_dbus(ctrl_mac, dev_mac)
                    device_path = scan_for_device_dbus(self, ctrl_mac, dev_mac)
                    if device_path:
                        if pair_device_by_path(device_path):
                            trust_device_dbus(ctrl_mac, dev_mac)
                            success = connect_device_dbus(ctrl_mac, dev_mac)
                        else:
                            log(f"❌ Retry pairing failed for {dev_mac}")
                    else:
                        log(f"❌ Retry scan failed for {dev_mac}")
                else:
                    log(f"❌ Unhandled connection error for {dev_mac}: {error_msg}")
        elif recommendation == "trust_and_connect":
            if trust_device_dbus(ctrl_mac, dev_mac):
                success = connect_device_dbus(ctrl_mac, dev_mac)
        elif recommendation == "pair_and_connect":
            if not pair_device_dbus(ctrl_mac, dev_mac):
                log(f"⚠️ Initial pairing failed — will try removing and scanning.")
                remove_device_dbus(ctrl_mac, dev_mac)
                device_path = scan_for_device_dbus(self, ctrl_mac, dev_mac)

                if device_path:
                    log(f"🔎 Found {dev_mac} again during scan — retrying full pair/trust/connect.")
                    if pair_device_by_path(device_path):
                        trust_device_dbus(ctrl_mac, dev_mac)
                        success = connect_device_dbus(ctrl_mac, dev_mac)
                    else:
                        log(f"❌ Pairing failed again for {dev_mac} — unable to connect.")
                        self.expected_devices.discard(dev_mac)
                        return
                else:
                    log(f"❌ Scan could not rediscover {dev_mac}")
            else:
                trust_device_dbus(ctrl_mac, dev_mac)
                success = connect_device_dbus(ctrl_mac, dev_mac)
        elif recommendation == "run discovery":
            remove_device_dbus(ctrl_mac, dev_mac)
            device_path  = scan_for_device_dbus(self, ctrl_mac, dev_mac)

            if device_path:
                log(f"Found {dev_mac} during scan — attempting pair/trust/connect")
                if pair_device_by_path(device_path):
                    trust_device_dbus(ctrl_mac, dev_mac)
                    success = connect_device_dbus(ctrl_mac, dev_mac)
                else:
                    log(f"❌ Pairing failed after rediscovery — likely not in pairing mode")
            else:
                log(f"Scan did not find {dev_mac}")


        if success:
            latency = 100  # You can pull from saved settings later
            pactl_sink = f"bluez_sink.{dev_mac.replace(':', '_')}.a2dp_sink"
            if create_loopback(pactl_sink, latency):
                log(f"Loopback created for {dev_mac} → {pactl_sink}")
                self.loopbacks_created.add(dev_mac)
        else:
            log(f"Failed to reconnect {dev_mac}")

    def analyze_device(self, ctrl_mac, dev_mac):
        update_bluetooth_state()
        ctrl = GLOBAL_BLUETOOTH_STATE.get("controllers", {}).get(ctrl_mac)
        if not ctrl:
            return "run discovery"

        device = ctrl.get("devices", {}).get(dev_mac)
        if not device:
            return "run discovery"

        paired = device.get("paired")
        trusted = device.get("trusted")
        connected = device.get("connected")
        uuids = device.get("uuids", [])

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
    






def scan_for_device_dbus(agent, ctrl_mac: str, target_mac: str, timeout: int = 20) -> bool:
    with agent.scan_lock:
        now = time.time()
        if now - agent.last_scan_time < agent.scan_cooldown_sec:
            log(f"⏳ Scan for {target_mac} skipped — last run {now - agent.last_scan_time:.1f}s ago.")
            return False
        agent.last_scan_time = now

        

        try:
            bus = SystemBus()
            manager = bus.get("org.bluez", "/")
            objects = manager.GetManagedObjects()

            adapter_path = next(
                (path for path, ifaces in objects.items()
                if "org.bluez.Adapter1" in ifaces and
                ifaces["org.bluez.Adapter1"].get("Address", "").upper() == ctrl_mac.upper()), None)

            if not adapter_path:
                log(f"❌ Adapter for {ctrl_mac} not found.")
                return False

            adapter = bus.get("org.bluez", adapter_path)

            # Safe StopDiscovery
            try:
                adapter.StopDiscovery()
                time.sleep(1)
            except Exception as e:
                if "InProgress" in str(e):
                    log(f"⏳ Discovery already running, skipping StopDiscovery.")
                else:
                    log(f"⚠️ Failed StopDiscovery: {e}")


            disable_discovery_on_all_adapters(bus, ctrl_mac)
            # StartDiscovery
            try:
                adapter.StartDiscovery()
            except Exception as e:
                if "InProgress" in str(e):
                    log("⏳ StartDiscovery already running, continuing anyway...")
                else:
                    log(f"❌ StartDiscovery failed: {e}")
                    return False

            log(f"🔍 Scanning for {target_mac} on {ctrl_mac}...")
            start_time = time.time()

            while time.time() - start_time < timeout:
                objects = manager.GetManagedObjects()
                for path, ifaces in objects.items():
                    dev = ifaces.get("org.bluez.Device1")
                    if dev and dev.get("Address", "").upper() == target_mac.upper():
                        # ✅ NEW: Ensure device was found under *correct controller* only
                        if not path.startswith(adapter_path):
                            log(f"⚠️ Skipping {target_mac} — found under wrong controller: {path}")
                            continue
                        log(f"✅ Device {target_mac} found at {path} on {ctrl_mac} — scan success")
                        try:
                            adapter.StopDiscovery()
                        except Exception as e:
                            log(f"⚠️ Early StopDiscovery failed: {e}")
                        return path

                time.sleep(1)

            # Timeout fallback
            try:
                adapter.StopDiscovery()
            except Exception as e:
                log(f"⚠️ Post-scan StopDiscovery failed: {e}")

            return False

        except Exception as e:
            log(f"❌ scan_for_device_dbus failed: {e}")
            return False




# # D-Bus device interaction helpers
# def get_device_path(ctrl_mac, dev_mac):
#     bus = SystemBus()
#     manager = bus.get("org.bluez", "/")
#     objects = manager.GetManagedObjects()

#     for path, ifaces in objects.items():
#         if "org.bluez.Adapter1" in ifaces:
#             if ifaces["org.bluez.Adapter1"].get("Address", "").upper() == ctrl_mac.upper():
#                 adapter_path = path
#                 mac_fragment = dev_mac.replace(":", "_")
#                 dev_path = f"{adapter_path}/dev_{mac_fragment}"
#                 return dev_path if dev_path in objects else None
#     return None
def get_device_path(dev_mac: str) -> str | None:
    """
    Finds the D-Bus device path for the given device MAC address,
    searching all adapters. Returns the full path if found, or None.
    """
    bus = SystemBus()
    manager = bus.get("org.bluez", "/")
    objects = manager.GetManagedObjects()

    dev_mac_upper = dev_mac.upper().replace(":", "_")

    for path in objects:
        if path.endswith(f"dev_{dev_mac_upper}"):
            return path  # This is the full D-Bus path to the device

    log(f"❌ Device {dev_mac} not found in any adapter.")
    return None

def disable_discovery_on_all_adapters(bus, target_mac):
    manager = bus.get("org.bluez", "/")
    objects = manager.GetManagedObjects()

    for path, ifaces in objects.items():
        if "org.bluez.Adapter1" in ifaces:
            addr = ifaces["org.bluez.Adapter1"].get("Address", "").upper()
            adapter = bus.get("org.bluez", path)
            try:
                if addr != target_mac:
                    adapter.Discoverable = False
                    adapter.Pairable = False
                    adapter.Powered = True
                    try:
                        adapter.StopDiscovery()
                        log(f"✅ Stopped discovery on adapter {addr}")
                    except Exception as e:
                        if "No discovery started" not in str(e):
                            log(f"⚠️ Could not stop discovery on {addr}: {e}")
            except Exception as e:
                log(f"⚠️ Failed to disable discoverability or stop scan on {addr}: {e}")




def connect_device_dbus(ctrl_mac, dev_mac):
    try:
        path = get_device_path(dev_mac)
        log(f"🔌 Attempting to connect to device path: {path}")
        if not path:
            log(f"Device path not found for {dev_mac} under {ctrl_mac}")
            return False
        device = SystemBus().get("org.bluez", path)
        device.Connect()
        return True
    except Exception as e:
        log(f"connect_device_dbus failed: {e}")
        return False

def trust_device_dbus(ctrl_mac, dev_mac):
    try:
        path = get_device_path(dev_mac)
        log(f"🔌 Attempting to trust to device path: {path}")
        if not path:
            return False
        device = SystemBus().get("org.bluez", path)
        device.Trusted = True
        return True
    except Exception as e:
        log(f"trust_device_dbus failed: {e}")
        return False

def pair_device_dbus(ctrl_mac, dev_mac):
    try:
        path = get_device_path(dev_mac)
        log(f"🔌 Attempting to pair to device path: {path}")
        if not path:
            log(f"❌ No device path found for {dev_mac} on {ctrl_mac} — device may not be ready in BlueZ yet.")
            return False
        time.sleep(1.5) 
        device = SystemBus().get("org.bluez", path)
        device.Pair()
        log(f"🔗 Pairing {dev_mac} on {ctrl_mac} worked")
        return True
    except Exception as e:
        log(f"pair_device_dbus failed: {e}")
        return False

def pair_device_by_path(path: str) -> bool:
    try:
        time.sleep(1.5)  # allow BlueZ to settle
        device = SystemBus().get("org.bluez", path)
        device.Pair()
        return True
    except Exception as e:
        log(f"pair_device_by_path failed for {path}: {e}")
        return False

def remove_device_dbus(ctrl_mac, dev_mac):
    try:
        bus = SystemBus()
        manager = bus.get("org.bluez", "/")
        objects = manager.GetManagedObjects()
        for path, ifaces in objects.items():
            if "org.bluez.Adapter1" in ifaces:
                if ifaces["org.bluez.Adapter1"].get("Address", "").upper() == ctrl_mac.upper():
                    adapter = bus.get("org.bluez", path)
                    dev_path = f"{path}/dev_{dev_mac.replace(':', '_')}"
                    adapter.RemoveDevice(dev_path)
                    return True
        return False
    except Exception as e:
        log(f"remove_device_dbus failed: {e}")
        return False
    


def connect_one_plan(
    target_mac: str,
    allowed_macs: list[str]
) -> tuple[str, str, list[tuple[str, str]]]:
    target_mac = target_mac.upper()
    allowed_macs = [m.upper() for m in allowed_macs]
    disconnect_list = []
    used_controllers = set()
    target_connected_on = []
    config_speaker_usage = {}

    log(f"🔍 Planning connection for target: {target_mac}")
    log(f"🎯 Allowed MACs in config: {allowed_macs}")

    for ctrl_mac, ctrl_data in GLOBAL_BLUETOOTH_STATE["controllers"].items():
        log(f"🧭 Scanning controller {ctrl_mac} (hci={ctrl_data['hci']})")

        if ctrl_data["hci"] == "hci0":
            log(f"  ↪️ Skipping controller {ctrl_mac} (reserved for phone)")
            continue

        for dev_mac in ctrl_data.get("connected", []):
            dev_mac = dev_mac.upper()
            log(f"    🔗 Found connected device: {dev_mac} on {ctrl_mac}")

            # Track how many controllers each config device is using
            if dev_mac in allowed_macs:
                config_speaker_usage.setdefault(dev_mac, []).append(ctrl_mac)

            # Case 1: Target is already connected
            if dev_mac == target_mac:
                target_connected_on.append(ctrl_mac)
                log(f"    ✅ Target {dev_mac} already connected on {ctrl_mac}")

            # Case 2: Out-of-config speaker (not in config)
            elif dev_mac not in allowed_macs:
                disconnect_list.append((dev_mac, ctrl_mac))
                log(f"    ❌ Out-of-config device {dev_mac} → add to disconnect list")

            # Case 3: Config speaker taking up controller
            elif dev_mac in allowed_macs:
                used_controllers.add(ctrl_mac)
                log(f"    ☑️ Config speaker {dev_mac} occupies controller {ctrl_mac}")

    log(f"📡 Target is currently connected on: {target_connected_on}")
    log(f"🧹 Disconnect list built: {disconnect_list}")
    log(f"🧾 Controllers in use by config devices: {used_controllers}")

    # --- Handle multiple connections of target ---
    if len(target_connected_on) == 1:
        log(f"🟢 Only one controller has the target — no reconnect needed.")
        return "already_connected", target_connected_on[0], disconnect_list

    elif len(target_connected_on) > 1:
        controller_to_keep = target_connected_on[0]
        for ctrl_mac in target_connected_on[1:]:
            disconnect_list.append((target_mac, ctrl_mac))
        log(f"🟡 Target connected on multiple controllers, keeping {controller_to_keep}, disconnecting from others")
        return "already_connected", controller_to_keep, disconnect_list

    # --- No controllers currently hosting the target ---
    # Try to find a truly free one first
    for ctrl_mac, ctrl_data in GLOBAL_BLUETOOTH_STATE["controllers"].items():
        if ctrl_data["hci"] == "hci0":
            continue
        if ctrl_mac not in used_controllers:
            log(f"🔓 Found free controller for connection: {ctrl_mac}")
            return "needs_connection", ctrl_mac, disconnect_list

    # --- All are in use — check for duplicate config speakers ---
    for mac, ctrl_list in config_speaker_usage.items():
        if len(ctrl_list) > 1:
            # Free one controller from this duplicate
            ctrl_to_free = ctrl_list[1]
            disconnect_list.append((mac, ctrl_to_free))
            log(f"🔁 Config speaker {mac} is using multiple controllers — freeing up {ctrl_to_free} for {target_mac}")
            return "needs_connection", ctrl_to_free, disconnect_list

    # Still no options
    log(f"🔴 No available controller found for {target_mac}")
    return "error", "", disconnect_list

agent = ConnectionAgent()
agent.start()



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
    
# Start agent
if __name__ == '__main__':
 
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        agent.stop()
