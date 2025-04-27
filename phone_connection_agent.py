#!/usr/bin/env python3
import sys
import logging
import signal
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

# ── Configuration ─────────────────────────────────────────────────────────────

BLUEZ        = "org.bluez"
ADAPTER      = "hci0"
AGENT_PATH   = "/com/syncsonic/pair_agent"
CAPABILITY   = "NoInputNoOutput"
IDLE_TIMEOUT = 60  # seconds

# ── Logging Setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-7s %(message)s"
)
logger = logging.getLogger(__name__)

# ── Pairing Agent Definition ─────────────────────────────────────────────────

class PairingAgent(dbus.service.Object):
    def __init__(self, bus, path):
        super().__init__(bus, path)
        logger.debug(f"Agent initialized at {path}")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        logger.debug("Agent.Release() called")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        logger.debug(f"Agent.AuthorizeService(device={device}, uuid={uuid}) → YES")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        logger.debug(f"Agent.RequestConfirmation(device={device}, passkey={passkey}) → YES")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        logger.debug(f"Agent.RequestPinCode(device={device}) → '0000'")
        return "0000"

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        logger.debug(f"Agent.RequestPasskey(device={device}) → 0")
        return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def DisplayPasskey(self, device, passkey):
        logger.debug(f"Agent.DisplayPasskey(device={device}, passkey={passkey})")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        logger.debug(f"Agent.DisplayPinCode(device={device}, pincode={pincode})")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        logger.debug(f"Agent.RequestAuthorization(device={device}) → YES")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        logger.debug("Agent.Cancel() called")

# ── Helper to flip adapter flags ───────────────────────────────────────────────

def set_adapter_property(bus, prop, value):
    obj   = bus.get_object(BLUEZ, f"/org/bluez/{ADAPTER}")
    props = dbus.Interface(obj, dbus.PROPERTIES_IFACE)
    props.Set("org.bluez.Adapter1", prop, value)
    logger.debug(f"Adapter property {prop} set to {value}")

# ── Signal Callbacks ──────────────────────────────────────────────────────────

def on_props_changed(interface, changed, invalidated, path):
    logger.debug(f"[PropertiesChanged] path={path}, iface={interface}, changed={changed}, invalidated={invalidated}")

def on_interfaces_added(path, interfaces):
    logger.debug(f"[InterfacesAdded] path={path}, interfaces={list(interfaces.keys())}")

# ── Main Entrypoint ───────────────────────────────────────────────────────────

def main():
    # 1) Initialize D-Bus mainloop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # 2) Subscribe to signals for visibility
    bus.add_signal_receiver(
        on_props_changed,
        dbus_interface="org.freedesktop.DBus.Properties",
        signal_name="PropertiesChanged",
        path_keyword="path"
    )
    bus.add_signal_receiver(
        on_interfaces_added,
        dbus_interface="org.freedesktop.DBus.ObjectManager",
        signal_name="InterfacesAdded",
        path="/org/bluez",
        path_keyword="path"
    )

    # 3) Register our Agent
    agent = PairingAgent(bus, AGENT_PATH)
    bluez_obj = bus.get_object(BLUEZ, "/org/bluez")
    manager   = dbus.Interface(bluez_obj, "org.bluez.AgentManager1")

    manager.RegisterAgent(AGENT_PATH, CAPABILITY)
    manager.RequestDefaultAgent(AGENT_PATH)
    logger.info(f"Registered agent {AGENT_PATH} with capability={CAPABILITY}")

    # 4) Enable Powered, Pairable, Discoverable
    set_adapter_property(bus, "Powered",     dbus.Boolean(1))
    set_adapter_property(bus, "Pairable",    dbus.Boolean(1))
    set_adapter_property(bus, "Discoverable", dbus.Boolean(1))
    logger.info("Adapter is Powered, Pairable, and Discoverable")

    # 5) Prepare our GLib MainLoop
    loop = GLib.MainLoop()
    has_unregistered = False

    def shutdown(*args):
        nonlocal has_unregistered
        if not has_unregistered:
            try:
                manager.UnregisterAgent(AGENT_PATH)
                logger.info("Agent unregistered")
            except dbus.exceptions.DBusException as e:
                if "DoesNotExist" not in str(e):
                    logger.warning(f"UnregisterAgent failed: {e}")
            has_unregistered = True
        loop.quit()
        return False  # stop any further timeout callbacks

    # 6) Hook SIGINT and idle timeout
    signal.signal(signal.SIGINT, lambda sig, frame: shutdown())
    GLib.timeout_add_seconds(IDLE_TIMEOUT, shutdown)

    logger.info("Waiting for pairing… (Ctrl-C or idle timeout will stop)")
    loop.run()
    sys.exit(0)

if __name__ == "__main__":
    main()
