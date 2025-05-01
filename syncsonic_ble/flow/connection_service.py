# connection_service.py
"""connection_service
====================
Thread‑safe orchestrator that owns **all** Bluetooth logic:

* Maintains the *expected speaker* set.
* Uses :pyclass:`scan_manager.ScanManager` to serialise discovery.
* Runs **one** background worker thread that consumes intents from a
  `queue.Queue` – so every BlueZ call happens in that single thread.
* Can be driven by any transport: Flask today, BLE tomorrow.
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from queue import Queue, Empty
from typing import Dict, List, Tuple

from syncsonic_ble.infra.bus_manager import get_bus
from syncsonic_ble.flow.scan_manager import ScanManager
from syncsonic_ble.flow.connect_planner import connect_one_plan  # rename of your existing file
from syncsonic_ble.core.bt_helpers import (                      # thin wrappers around DBus ops
    disconnect_device_dbus,
    connect_device_dbus,
    pair_device_dbus,
    trust_device_dbus,
    remove_device_dbus,
)
from utils.pulseaudio_service import create_loopback, remove_loopback_for_device, setup_pulseaudio
from ..logging_conf import get_logger
import subprocess, time
from ..constants import (Msg, DBUS_PROP_IFACE, DEVICE_INTERFACE, ADAPTER_INTERFACE, BLUEZ_SERVICE_NAME)
from ..core.characteristic import Characteristic
from dbus import Interface
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public intent enum + shared queue
# ---------------------------------------------------------------------------

class Intent(Enum):
    CONNECT_ONE  = auto()   # expects keys: mac, friendly_name, allowed
    DISCONNECT   = auto()   # expects key: mac
    SET_EXPECTED = auto()   # expects key: list[str]
    LOOPBACK_SYNC = auto()  # expects key: {"mac": <str>, "connected": <bool>}


work_q: Queue[Tuple[Intent, Dict]] = Queue()  # one global queue

# ---------------------------------------------------------------------------
# ConnectionService implementation
# ---------------------------------------------------------------------------

class ConnectionService:
    """Singleton‑style orchestrator (but caller holds the reference)."""

    # You almost certainly want exactly **one** instance – create at startup.

    def __init__(self):
        self.bus  = get_bus()          # singleton, thread‑safe
        self.scan = ScanManager()      # owns discovery

        self.bus.subscribe(
            iface="org.freedesktop.DBus.Properties",
            signal="PropertiesChanged",
            object="/org/bluez",
            signal_fired=self._on_props_changed,
        )

        self.expected: set[str] = set()
        self.loopbacks: set[str] = set()  # macs that already have loopbacks

        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()
        self._char = None  # will be injected later
        logger.info("ConnectionService worker thread started")

    # -----------------------------
    # Public helper: enqueue intents
    # -----------------------------

    def submit(self, intent: Intent, payload: Dict):
        """Called by *any* transport thread (Flask / BLE etc.)."""
        work_q.put((intent, payload))

    # ------------------------------------------------------------------
    #  BlueZ signal helpers
    #
    #  • _extract_mac(path)       – pull “AA:BB:CC:DD:EE:FF” out of a
    #    BlueZ object path like “…/dev_AA_BB_CC_DD_EE_FF”.
    #
    #  • _on_props_changed(...)   – runs in the GLib thread whenever
    #    BlueZ fires PropertiesChanged.  If the signal toggles the
    #    Connected flag for one of our *expected* speakers, we enqueue a
    #    LOOPBACK_SYNC intent so the worker thread can create/remove the
    #    loopback safely and in order.
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_mac(path: str) -> str | None:
        if "dev_" not in path:
            return None
        return path.split("/")[-1].replace("dev_", "").replace("_", ":").upper()

    def _on_props_changed(self, sender, obj_path, iface, signal, params):
        #logger.info(f"PROP signal {mac} Connected={connected}")

        # Params is a GLib Variant → unpack to tuple
        changed_iface, changed_dict, _invalidated = params

        # We only care about Device1 property changes
        if changed_iface != "org.bluez.Device1":
            return

        mac = self._extract_mac(obj_path)
        if not mac or "Connected" not in changed_dict:
            return
        if mac.upper() not in self.expected:
            return

        connected = bool(changed_dict["Connected"])
        work_q.put((
            Intent.LOOPBACK_SYNC,
            {"mac": mac.upper(), "connected": connected}
        ))


    # -----------------------------
    # Worker loop (runs in its own thread)
    # -----------------------------

    def _run_worker(self):  # noqa: C901 – complexity is okay for now
        while True:
            try:
                intent, payload = work_q.get(timeout=1)
            except Empty:
                continue
            

            if intent is Intent.SET_EXPECTED:
                macs: List[str] = [m.upper() for m in payload["macs"]]
                replace: bool = payload.get("replace", False)
                if replace:
                    self.expected = set(macs)
                else:
                    self.expected.update(macs)
                logger.info(f"Expected set now {self.expected}")

            elif intent is Intent.CONNECT_ONE:
                mac   = payload["mac"].upper()
                allow = [m.upper() for m in payload["allowed"]]

                self.expected.add(mac)          # so loopback sync recognises it



                # # Re‑evaluate object tree each time

                obj_mgr = self.bus.get("org.bluez", "/").GetManagedObjects()
                status, ctrl_mac, dc_list = connect_one_plan(mac, allow, obj_mgr)

                

                for dev_mac, adapter_mac in dc_list:
                    path = self._device_path(adapter_mac, dev_mac)
                    disconnect_device_dbus(path, dev_mac, self.bus)
                
                if status == "already_connected":
                    sink = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
                    A2DP_UUID = "0000110b-0000-1000-8000-00805f9b34fb"
                    # use ctrl_mac (the HCI) and mac (the device) instead
                    device_path = self._device_path(ctrl_mac, mac)
                    raw_obj     = self.bus.get(BLUEZ_SERVICE_NAME, device_path)
                    dev_iface   = Interface(raw_obj, DEVICE_INTERFACE)

                    logger.info(f"→ [DEBUG] Asking BlueZ to connect A2DP on {device_path}")
                    try:
                        dev_iface.ConnectProfile(A2DP_UUID)
                        logger.info("→ [DEBUG] ConnectProfile(A2DP) succeeded")
                    except Exception as e:
                        logger.info(f"⚠️ ConnectProfile(A2DP) failed: {e}")
                                    

                     # signal connect success
                    if self._char:
                        self._char.send_notification(
                            Msg.CONNECTION_STATUS_UPDATE,
                            {"phase": "connect_success", "device": mac}
                        )

                    if mac not in self.loopbacks:
                        if create_loopback(sink):
                            self.loopbacks.add(mac)
                            logger.info(f"✅ Loopback created for already-connected {mac}")
                    # we’re done; nothing else to do for this intent
                    continue

                if status == "needs_connection" and ctrl_mac:
                    self._try_reconnect(ctrl_mac, mac)

            elif intent is Intent.DISCONNECT:
                mac = payload["mac"].upper()
                self._disconnect_everywhere(mac)

            elif intent is Intent.LOOPBACK_SYNC:
                mac        = payload["mac"]
                connected  = payload["connected"]
                sink       = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"

                if connected and mac not in self.loopbacks:
                    if create_loopback(sink):
                        self.loopbacks.add(mac)
                        logger.info(f"✅ Loopback autoprovisioned for {mac}")
                elif not connected and mac in self.loopbacks:
                    remove_loopback_for_device(mac)
                    self.loopbacks.remove(mac)
                    logger.info(f"🗑️  Loopback removed after disconnect for {mac}")


    # -----------------------------
    # Core helpers (same thread)
    # -----------------------------

    def _try_reconnect(self, adapter_mac: str, dev_mac: str):
        logger.info(f"FSM: reconnect {dev_mac} via {adapter_mac}")

        # NEW → ask the object tree what still needs doing
        state = self._analyze_device(adapter_mac, dev_mac)

        loopback_sink = f"bluez_sink.{dev_mac.replace(':', '_')}.a2dp_sink"
        device_path = self._device_path(adapter_mac, dev_mac)
        max_retry = 3
        attempt   = 0
        # send update to frontend
        if self._char:
            self._char.send_notification(
                Msg.CONNECTION_STATUS_UPDATE,
                {"phase": "fsm_start", "device": dev_mac}
            )
        while attempt < max_retry:
            logger.info(f"  → [{attempt+1}/3] state={state}")
            if self._char:
                self._char.send_notification(
                    Msg.CONNECTION_STATUS_UPDATE,
                    {
                        "phase": "fsm_state",
                        "device": dev_mac,
                        "state": state,
                        "attempt": attempt
                    }
                )

            # --- state handlers ---
            if state == "run_discovery":
                # signal discovery start
                if self._char:
                    self._char.send_notification(
                        Msg.CONNECTION_STATUS_UPDATE,
                        {"phase": "discovery_start", "device": dev_mac}
                    )
                try:
                    self.scan.ensure_discovery(adapter_mac)
                    path = self.scan.wait_for_device(adapter_mac, dev_mac, 20)
                finally:
                    self.scan.release_discovery(adapter_mac)

                if not path:
                    logger.info("discovery timeout")
                    # signal discovery failed
                    if self._char:
                        self._char.send_notification(
                            Msg.ERROR,
                            {"phase": "discovery_timeout", "device": dev_mac}
                        )
                    break
                # signal discovery success
                if self._char:
                    self._char.send_notification(
                        Msg.CONNECTION_STATUS_UPDATE,
                        {"phase": "discovery_complete", "device": dev_mac}
                    )
                device_path = path
                state = "pair"   

            elif state == "pair":
                # signal pairing start
                if self._char:
                    self._char.send_notification(
                        Msg.CONNECTION_STATUS_UPDATE,
                        {"phase": "pairing_start", "device": dev_mac}
                    )
                if pair_device_dbus(device_path, bus=self.bus):
                    state = "trust"
                    # signal pairing success
                    if self._char:
                        self._char.send_notification(
                            Msg.CONNECTION_STATUS_UPDATE,
                            {"phase": "pairing_success", "device": dev_mac}
                        )
                else:
                    attempt += 1
                    remove_device_dbus(device_path, self.bus)
                    logger.info("    ⚠️ pairing failed, removed device and retrying")
                    state = "run_discovery"  # remove & retry
                    # signal pairing failure
                    if self._char:
                        self._char.send_notification(
                            Msg.ERROR,
                            {"phase": "pairing_failed", "device": dev_mac, "attempt": attempt}
                        )

            elif state == "trust":
                trust_device_dbus(device_path, self.bus)
                state = "connect"
                # signal trusting start
                if self._char:
                    self._char.send_notification(
                        Msg.CONNECTION_STATUS_UPDATE,
                        {"phase": "trusting", "device": dev_mac}
                    )

            elif state == "connect":
                # signal connect start
                if self._char:
                    self._char.send_notification(
                        Msg.CONNECTION_STATUS_UPDATE,
                        {"phase": "connect_start", "device": dev_mac}
                    )

                if connect_device_dbus(device_path, self.bus):

                    device_path = self._device_path(adapter_mac, dev_mac)
                    raw_obj     = self.bus.get(BLUEZ_SERVICE_NAME, device_path)

                    # wrap it in the Device1 interface
                    dev_iface   = Interface(raw_obj, DEVICE_INTERFACE)

                    # A2DP Sink UUID
                    A2DP_UUID    = "0000110b-0000-1000-8000-00805f9b34fb"

                    logger.info(f"→ [DEBUG] Asking BlueZ to connect A2DP on {device_path}")
                    try:
                        dev_iface.ConnectProfile(A2DP_UUID)
                        logger.info("→ [DEBUG] ConnectProfile(A2DP) succeeded")
                    except Exception as e:
                        logger.info(f"⚠️ ConnectProfile(A2DP) failed: {e}")

                    # signal connect success
                    if self._char:
                        self._char.send_notification(
                            Msg.CONNECTION_STATUS_UPDATE,
                            {"phase": "connect_success", "device": dev_mac}
                        )
                    if create_loopback(loopback_sink):
                        self.loopbacks.add(dev_mac)
                        logger.info("    ✅ connected + loopback")
                        return
                    else:
                        logger.info("    ⚠️ connected but loopback creation failed")
                        if self._char:
                            self._char.send_notification(
                                Msg.ERROR,
                                {"phase": "loopback creation failed, click connect again", "device": dev_mac}
                            )
                        return
                    
                if self._char:
                    self._char.send_notification(
                        Msg.ERROR,
                        {"phase": "connect_failed", "device": dev_mac, "attempt": attempt}
                    )

                state = "pair"  # fall back
                attempt += 1

        logger.info(f"    ❌ failed to reconnect {dev_mac}")

    def _disconnect_everywhere(self, mac: str):
        obj_mgr = self.bus.get("org.bluez", "/").GetManagedObjects()
        for path, ifaces in obj_mgr.items():
            dev = ifaces.get("org.bluez.Device1")
            if dev and dev.get("Address", "").upper() == mac and dev.get("Connected", False):
                disconnect_device_dbus(path, mac, self.bus)
        if mac in self.loopbacks:
            remove_loopback_for_device(mac)
            self.loopbacks.remove(mac)

    def _analyze_device(self, adapter_mac: str, dev_mac: str) -> str:
        objects = self.bus.get("org.bluez", "/").GetManagedObjects()

        # Locate the Device1 dictionary for this mac *on the chosen adapter*
        dev_path = self._device_path(adapter_mac, dev_mac)
        dev = objects.get(dev_path, {}).get("org.bluez.Device1", {})

        if not dev:                       # nothing there → must discover
            return "run_discovery"

        paired     = dev.get("Paired",   False)
        trusted    = dev.get("Trusted",  False)
        connected  = dev.get("Connected",False)
        uuids      = dev.get("UUIDs",    [])

        has_audio  = any("110b" in u.lower() for u in uuids)  # A2DP/AVRCP

        if connected and has_audio:
            return "already_connected"
        if not paired:
            return "pair"
        if not trusted:
            return "trust"
        if paired and trusted and not connected:
            return "connect"
        return "run_discovery"

    # -----------------------------
    # Utility
    # -----------------------------

    def _device_path(self, ctrl_mac: str, dev_mac: str) -> str | None:
        """Return /org/bluez/hciX/dev_XX_YY_… for *dev_mac* on adapter *ctrl_mac*.
        ctrl_mac – adapter’s Bluetooth MAC address (e.g. BC:FC:E7:21:21:C6)
        dev_mac  – speaker MAC (e.g. 00:0C:8A:FF:18:FE)
        """
        objects = self.bus.get("org.bluez", "/").GetManagedObjects()

        dev_mac_fmt = dev_mac.upper().replace(":", "_")
        for path, ifaces in objects.items():
            if "org.bluez.Adapter1" in ifaces:
                addr = ifaces["org.bluez.Adapter1"].get("Address", "").upper()
                if addr == ctrl_mac.upper():
                    return f"{path}/dev_{dev_mac_fmt}"
        return None
