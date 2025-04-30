"""Utilities for selecting and resetting BlueZ adapters."""
from __future__ import annotations
import dbus, os, time
from gi.repository import GLib
from ..constants import (BLUEZ_SERVICE_NAME, ADAPTER_INTERFACE, DBUS_OM_IFACE,
                         DBUS_PROP_IFACE)
from ..logging_conf import get_logger

log = get_logger(__name__)

RESERVED_HCI = os.getenv("RESERVED_HCI")
if not RESERVED_HCI:
    raise RuntimeError("RESERVED_HCI environment variable not set – cannot pick phone adapter")

_BUS = None  # lazy‑loaded SystemBus instance; filled by gatt_server.main

def set_bus(bus):
    global _BUS
    _BUS = bus


def find_adapter(preferred: str | None = None):
    om = dbus.Interface(_BUS.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
    for path, ifaces in om.GetManagedObjects().items():
        if ADAPTER_INTERFACE not in ifaces:
            continue
        if preferred and path.split("/")[-1] != preferred:
            continue
        adapter = dbus.Interface(_BUS.get_object(BLUEZ_SERVICE_NAME, path), ADAPTER_INTERFACE)
        return path, adapter
    return None, None


def reset_adapter(adapter):
    """Power‑cycles adapter and waits a little.  No device cleanup here (ConnectionService does that)."""
    try:
        props = dbus.Interface(_BUS.get_object(BLUEZ_SERVICE_NAME, adapter.object_path), DBUS_PROP_IFACE)
        log.debug("Power‑cycling %s", adapter.object_path)
        props.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(False))
        time.sleep(2.0)
        props.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(True))
        GLib.idle_add(lambda: None)  # let mainloop breathe
        log.info("Adapter %s reset", adapter.object_path)
    except Exception as exc:
        log.error("Failed to reset adapter: %s", exc)