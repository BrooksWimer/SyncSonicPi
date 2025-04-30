#!/usr/bin/env python3
import sys
import logging
import signal
import traceback

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import os


reserved = os.getenv("RESERVED_HCI")
if not reserved:
    raise RuntimeError("RESERVED_HCI not set – cannot pick phone adapter")

# ── Configuration ────────────────────────────────────────────────────────
BLUEZ        = "org.bluez"
ADAPTER      = reserved
PHONE_AGENT_PATH   = "/com/syncsonic/pair_agent"
CAPABILITY   = "DisplayYesNo"
IDLE_TIMEOUT = 60   # seconds for idle exit

# ── Logging Setup ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-7s %(message)s"
)
logger = logging.getLogger(__name__)

# ── Helpers to configure adapter ─────────────────────────────────────────
def configure_adapter(bus):
    try:
        logger.info(f"Configuring adapter {ADAPTER}: Powered, Pairable, Discoverable")
        om  = bus.get_object(BLUEZ, "/")
        mgr = dbus.Interface(om, "org.freedesktop.DBus.ObjectManager")
        objs = mgr.GetManagedObjects()
        for path, ifaces in objs.items():
            if "org.bluez.Adapter1" not in ifaces:
                continue
            hci = path.rsplit('/',1)[-1]
            props = dbus.Interface(
                bus.get_object(BLUEZ, path),
                dbus.PROPERTIES_IFACE
            )
            if hci == ADAPTER:
                props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
                props.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(True))
                props.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(True))
                logger.debug(f"Set {hci}: Powered, Pairable, Discoverable = True")
        logger.info("Adapter configuration complete")
    except Exception as e:
        logger.error(f"Error configuring adapters: {e}")
        logger.debug(traceback.format_exc())

# ── Callbacks for signal logging ─────────────────────────────────────────
def on_properties_changed(interface, changed, invalidated, path):
    logger.info(
        f"PropertiesChanged: iface={interface}, path={path}, changed={changed}, invalidated={invalidated}"
    )

def on_interfaces_added(object_path, interfaces):
    logger.info(f"InterfacesAdded: path={object_path}, interfaces={list(interfaces.keys())}")

# ── Pairing Agent Implementation ─────────────────────────────────────────
class PhonePairingAgent(dbus.service.Object):
    def __init__(self, bus, path):
        super().__init__(bus, path)
        logger.info(f"Agent initialized at {path}")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        logger.info("Agent.Release() called")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        logger.info(f"Agent.AuthorizeService(device={device}, uuid={uuid}) called")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        logger.info(f"Agent.RequestConfirmation(device={device}, passkey={passkey}) called")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        logger.info(f"Agent.RequestPinCode(device={device}) called")
        return "0000"

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        logger.info(f"Agent.RequestPasskey(device={device}) called")
        return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def DisplayPasskey(self, device, passkey):
        logger.info(f"Agent.DisplayPasskey(device={device}, passkey={passkey}) called")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        logger.info(f"Agent.DisplayPinCode(device={device}, pincode={pincode}) called")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        logger.info(f"Agent.RequestAuthorization(device={device}) called")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        logger.info("Agent.Cancel() called")

# ── Main Entrypoint ─────────────────────────────────────────────────────
def main():
    logger.info("Starting debug D-Bus agent with adapter & pairing visibility...")
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    logger.debug("D-Bus SystemBus acquired")

    # 1) Configure adapter discoverability
    configure_adapter(bus)

    # 2) Register signal listeners for full visibility
    bus.add_signal_receiver(
        on_properties_changed,
        dbus_interface="org.freedesktop.DBus.Properties",
        signal_name="PropertiesChanged",
        path_keyword="path"
    )
    bus.add_signal_receiver(
        on_interfaces_added,
        dbus_interface="org.freedesktop.DBus.ObjectManager",
        signal_name="InterfacesAdded",
        path="/"
    )

    # 3) Register our NoInputNoOutput Agent1
    agent = PhonePairingAgent(bus, PHONE_AGENT_PATH)
    bluez_obj = bus.get_object(BLUEZ, "/org/bluez")
    manager = dbus.Interface(bluez_obj, "org.bluez.AgentManager1")
    try:
        manager.RegisterAgent(PHONE_AGENT_PATH, CAPABILITY)
        logger.info(f"Registered agent at {PHONE_AGENT_PATH} with capability={CAPABILITY}")
        manager.RequestDefaultAgent(PHONE_AGENT_PATH)
        logger.info("Agent set as default")
    except Exception as e:
        logger.error(f"Error registering agent: {e}")
        logger.debug(traceback.format_exc())
        sys.exit(1)

    # 4) Run main loop until canceled or timeout
    loop = GLib.MainLoop()
    def shutdown(*args):
        logger.info("Shutdown signal received, exiting...")
        try:
            manager.UnregisterAgent(PHONE_AGENT_PATH)
            logger.info("Agent unregistered")
        except Exception:
            pass
        loop.quit()
        return False

    signal.signal(signal.SIGINT, lambda *_: shutdown())
    GLib.timeout_add_seconds(IDLE_TIMEOUT, shutdown)

    logger.info(f"Entering main loop (idle timeout {IDLE_TIMEOUT}s)")
    try:
        loop.run()
    except Exception:
        logger.error("Exception in main loop", exc_info=True)
    finally:
        logger.info("Exiting application")
        sys.exit(0)

if __name__ == "__main__":
    main()
