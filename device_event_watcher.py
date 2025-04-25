
from gi.repository import GLib
from utils.logging import log
import threading

def extract_mac_from_path(path: str) -> str | None:
    try:
        if "dev_" not in path:
            return None
        return path.split("/")[-1].replace("dev_", "").replace("_", ":").upper()
    except Exception as e:
        log(f"⚠️ Failed to extract MAC from path: {e}")
        return None

class DeviceEventWatcher:
    def __init__(self, agent, bus):
        self.agent = agent  # ConnectionAgent reference
        self.bus = bus

    def start(self):
        log("🔌 DeviceEventWatcher starting...")

        self.bus.subscribe(
            iface="org.freedesktop.DBus.Properties",
            signal="PropertiesChanged",
            object="/org/bluez",
            signal_fired=self.on_properties_changed
        )

        self.bus.subscribe(
            iface="org.freedesktop.DBus.ObjectManager",
            signal="InterfacesAdded",
            object="/org/bluez",
            signal_fired=self.on_interface_added
        )

        self.bus.subscribe(
            iface="org.freedesktop.DBus.ObjectManager",
            signal="InterfacesRemoved",
            object="/org/bluez",
            signal_fired=self.on_interface_removed
        )

        # Run GLib main loop in a background thread
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        log("🌀 GLib event loop running")
        self.loop = GLib.MainLoop()
        self.loop.run()

    def on_properties_changed(self, interface, changed, invalidated, path):
        mac = extract_mac_from_path(path)
        if not mac:
            return

        log(f"🔄 PropertiesChanged for {mac}: {changed}")

        if "Connected" in changed:
            connected = changed["Connected"]
            if connected:
                log(f"✅ {mac} just connected — checking loopback...")
                self.agent.ensure_connected_loopback(mac)
            else:
                log(f"🔌 {mac} disconnected — cleaning up...")
                self.agent.cleanup_disconnected_device(mac)

    def on_interface_added(self, path, interfaces):
        mac = extract_mac_from_path(path)
        if not mac:
            return
        log(f"🆕 Interface added: {mac} — path: {path}")

    def on_interface_removed(self, path, interfaces):
        mac = extract_mac_from_path(path)
        if not mac:
            return
        log(f"❌ Interface removed: {mac} — path: {path}")
