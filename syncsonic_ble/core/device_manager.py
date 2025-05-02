"""Tracks BlueZ Device objects, handles connect/disconnect, loopbacks."""
from __future__ import annotations

import dbus
from gi.repository import GLib
from typing import Dict, Set

from ..logging_conf import get_logger
from ..constants import (
    BLUEZ_SERVICE_NAME,
    DBUS_OM_IFACE, DBUS_PROP_IFACE,
    DEVICE_INTERFACE, ADAPTER_INTERFACE,
)
from ..utils.pulseaudio_service import create_loopback, remove_loopback_for_device
from ..constants import Msg

log = get_logger(__name__)

class DeviceManager:
    """Single source of truth for device state on one adapter."""

    def __init__(self, bus: dbus.SystemBus, adapter_path: str):
        self.bus: dbus.SystemBus = bus
        self.adapter_path: str   = adapter_path

        # runtime state ------------------------------------------------------
        self.devices: Dict[str, Dict] = {}
        self.reconnect_attempts: Dict[str, int] = {}
        self.max_reconnect_attempts: int = 3
        self.pairing_in_progress: Set[str] = set()
        self.connected: Set[str] = set()
        self.expected: set[str] = set()
        self._status: Dict[str, Dict] = {}
        self._char   = None            # will be injected later
        self.scanning = False          # set to True when scanning for devices
        self._setup_monitoring()

    # ─────────────────────────── helpers ────────────────────────────────────
    @staticmethod
    def _extract_mac(path: str) -> str | None:
        if "dev_" not in path:
            return None
        return path.split("/")[-1].replace("dev_", "").replace("_", ":").upper()

    def _devices_on_adapter(self, adapter_prefix: str) -> list[str]:
        """Return MACs currently *Connected* under that adapter."""
        om  = self.bus.get_object(BLUEZ_SERVICE_NAME, "/")
        mgr = dbus.Interface(om, DBUS_OM_IFACE)
        objs = mgr.GetManagedObjects()

        result: list[str] = []
        for obj_path, ifaces in objs.items():
            dev = ifaces.get(DEVICE_INTERFACE)
            if not dev or not dev.get("Connected", False):
                continue
            if obj_path.startswith(adapter_prefix):
                result.append(dev["Address"])
        return result

    # ───────────────────────── public API ───────────────────────────────────
    def attach_characteristic(self, char):
        """Inject the Characteristic so we can push status updates."""
        self._char = char

    # ────────────────────────── monitoring ─────────────────────────────────
    def _setup_monitoring(self):
        self.bus.add_signal_receiver(
            self._interfaces_added,
            dbus_interface="org.freedesktop.DBus.ObjectManager",
            signal_name="InterfacesAdded",
        )
        self.bus.add_signal_receiver(
            self._properties_changed,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path_keyword="path",
        )

    # D‑Bus callbacks --------------------------------------------------------
    def _interfaces_added(self, path, interfaces):
        if DEVICE_INTERFACE in interfaces:
            self._device_found(path)

    def _properties_changed(self, interface, changed, invalidated, path):
        if interface != DEVICE_INTERFACE or "Connected" not in changed:
            return

        connected = bool(changed["Connected"])
        mac       = self._extract_mac(path)
        if not mac:
            return

        log.info("[BlueZ] %s is now %s", mac,
                 "✓ CONNECTED" if connected else "✗ DISCONNECTED")

        if connected:
            self._handle_new_connection(path, mac)
        else:
            self._handle_disconnection(mac)

        # push status update -------------------------------------------------
        alias = changed.get("Alias", mac)
        self._status[mac] = {"alias": alias, "connected": connected}
        if self._char:
            self._char.push_status({"connected": list(self.connected)})

    # ───────────────────────── connection helpers ───────────────────────────
    def _handle_new_connection(self, path: str, mac: str):
        if mac in self.connected:
            return  # duplicate signal

        dev_obj   = self.bus.get_object(BLUEZ_SERVICE_NAME, path)
        dev_props = dbus.Interface(dev_obj, DBUS_PROP_IFACE)

        
        # A2DP check ---------------------------------------------------------
        try:
            uuids = dev_props.Get(DEVICE_INTERFACE, "UUIDs")
        except Exception:
            uuids = []
        if not any("110b" in u.lower() for u in uuids):
            log.info("%s lacks A2DP – skipping", mac)
            return

        adapter_prefix = "/".join(path.split("/")[:4])
        others = [m for m in self._devices_on_adapter(adapter_prefix) if m != mac]
        if others:
            # another speaker already owns that controller
            other_path = f"{adapter_prefix}/dev_{others[0].replace(':','_')}"
            dbus.Interface(dev_obj, DEVICE_INTERFACE).Disconnect()
            from syncsonic_ble.core.bt_helpers import remove_device_dbus
            remove_device_dbus(other_path, others[0], self.bus)
            log.warning("%s tried adapter %s but %s is already there. Disconnecting and removing", mac, adapter_prefix, others[0])
            return


        # auto‑connect profile if transport missing --------------------------
        _ensure_media_transport(self.bus, dev_obj, mac)

        # finally create loopback & mark connected ---------------------------
        sink_name = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
        create_loopback(sink_name)
        self.connected.add(mac)
        log.info("Created loopback for %s", mac)

    def _handle_disconnection(self, mac: str):
        if mac not in self.connected:
            return
        self.connected.remove(mac)
        remove_loopback_for_device(mac)
        log.info("%s disconnected – %d speaker(s) left", mac, len(self.connected))

    # ───────────────────────── misc helpers ─────────────────────────────────
    def _device_found(self, path: str):
        mac = self._extract_mac(path)
        if not mac:
            return
        # STREAMING SCAN MODE: broadcast each found device
        if self.scanning and self._char:
            obj = self.bus.get_object(BLUEZ_SERVICE_NAME, path)
            props = dbus.Interface(obj, DBUS_PROP_IFACE)
            name = props.Get(DEVICE_INTERFACE, "Alias") or props.Get(DEVICE_INTERFACE, "Name")
            paired = bool(props.Get(DEVICE_INTERFACE, "Paired"))
            device_info = {"mac": mac, "name": name, "paired": paired}
            log.info("→ [SCAN STREAM] Discovered %s (%s), paired=%s", name, mac, paired)
            self._char.send_notification(Msg.SCAN_DEVICES, {"device": device_info})
            return
        # NORMAL mode: only expected speakers
        if mac.upper() not in self.connected:
            log.debug("Ignoring un-expected device %s (%s)", path, mac)
            return
        obj = self.bus.get_object(BLUEZ_SERVICE_NAME, path)
        props_iface = dbus.Interface(obj, DBUS_PROP_IFACE)
        dev_iface   = dbus.Interface(obj, DEVICE_INTERFACE)
        self.devices[path] = {"device": obj, "props": props_iface, "iface": dev_iface}
        log.info("Registered expected speaker %s at %s", mac, path)

# helper – ensure MediaTransport exists before we create loopback ------------

def _ensure_media_transport(bus: dbus.SystemBus, dev_obj, mac: str):
    from ..constants import DBUS_OM_IFACE
    om  = bus.get_object(BLUEZ_SERVICE_NAME, "/")
    mgr = dbus.Interface(om, DBUS_OM_IFACE)
    objs = mgr.GetManagedObjects()
    fmt = mac.replace(":", "_")
    has_transport = any(
        "org.bluez.MediaTransport1" in ifaces and fmt in path
        for path, ifaces in objs.items()
    )
    if not has_transport:
        try:
            dbus_iface = dbus.Interface(dev_obj, DEVICE_INTERFACE)
            dbus_iface.ConnectProfile("0000110b-0000-1000-8000-00805f9b34fb")
            log.info("Triggered A2DP ConnectProfile for %s", mac)
        except Exception as exc:
            log.error("ConnectProfile failed for %s: %s", mac, exc)