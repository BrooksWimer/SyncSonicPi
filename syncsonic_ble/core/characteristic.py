"""GATT characteristic that carries our JSON command protocol."""
from __future__ import annotations

import json, subprocess, dbus
from typing import Dict, Any
from ..flow.scan_manager import ScanManager
from ..logging_conf import get_logger
from ..constants import (
    GATT_CHRC_IFACE, DBUS_PROP_IFACE, GATT_SERVICE_IFACE, DEVICE_INTERFACE,
    Msg, CHARACTERISTIC_UUID, DBUS_OM_IFACE, ADAPTER_INTERFACE
)

from ..utils.pulseaudio_service import create_loopback, remove_loopback_for_device
from ..endpoints.volume import set_stereo_volume
import os
import time
from ..constants import BLUEZ_SERVICE_NAME

log = get_logger(__name__)




class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        # build the object path under the service
        self.path = f"{service.get_path()}/char{index}"
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.service = service
        self.value = [dbus.Byte(0)] * 5
        self.notifying = False
        self.connected_devices = set()
        self.device_manager = None
        self._scan_mgr = None
        self._scan_adapter_mac = None
        super().__init__(bus, self.path)

        log.info("Characteristic created (%s)", uuid)


     # ───────────────────── allow device manager ────────────────────────────
    def set_device_manager(self, device_manager):
        """Give me a handle to the DeviceManager so I can call back on it."""
        self.device_manager = device_manager

    


    # ───────────────────── notification helpers ────────────────────────────
    def send_notification(self, msg_type: Msg, payload: Dict[str, Any]):
        """
        Encode *payload* under the given message type and send it as a BLE notification,
        if the client has enabled notifications.
        """
        # 1) Build the byte array
        data = self._encode(msg_type, payload)

        # 2) Log everything for full visibility
        log.info(
            "→ [BLE Notify] type=%s(0x%02x) payload=%s",
            msg_type.name,
            msg_type.value,
            payload
        )

        # 3) Actually send if the client has turned on notifications
        if self.notifying:
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {"Value": dbus.Array(data, signature="y")},
                []
            )

    # You can keep push_status as a thin wrapper for backward compatibility:
    def push_status(self, payload: Dict[str, Any]):
        self.send_notification(Msg.SUCCESS, payload)

    # ────────────────────── D‑Bus boilerplate ───────────────────────────────
    def get_properties(self):
        from ..constants import GATT_SERVICE_IFACE
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
                "Value": self.value,
                "Notifying": dbus.Boolean(self.notifying),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if prop == "Value":
            return dbus.Array(self.value, signature="y")
        return None

    # ───────────────────── Read/Write implementation ‑‑ JSON protocol ───────
    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        # verify backend is recieving notificatios
        log.info("💥 Backend WriteValue fired! raw value=%s options=%s", value, options)
        # CCCD write? ---------------------------------------------------------
        if len(value) == 2 and value[0] == 0x01:
            self.notifying = (value[1] == 0x01)
            log.info("Notifications %s via CCCD", "enabled" if self.notifying else "disabled")
            return

        # normal command ------------------------------------------------------
        msg_type, data = self._decode(value)
        handler = {
            Msg.PING:            self._handle_ping,
            Msg.CONNECT_ONE:     self._handle_connect_one,
            Msg.DISCONNECT:      self._handle_disconnect,
            Msg.SET_LATENCY:     self._handle_set_latency,
            Msg.SET_VOLUME:      self._handle_set_volume,
            Msg.GET_PAIRED_DEVICES: self._handle_get_paired,
            Msg.SET_MUTE:        self._handle_set_mute,
            Msg.SCAN_START:      self._handle_scan_start,
            Msg.SCAN_STOP:       self._handle_scan_stop,
        }.get(msg_type, self._unknown)

        response = handler(data)
        self.value = response
        if self.notifying:
            self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": dbus.Array(self.value)}, [])

    # ───────────────────── protocol helpers ---------------------------------
    def _encode(self, msg: Msg, payload: Dict[str, Any]):
        raw = json.dumps(payload).encode()
        out  = [dbus.Byte(msg)] + [dbus.Byte(b) for b in raw]
        return out

    def _decode(self, value):
        try:
            msg = Msg(value[0])
            if len(value) == 1:
                return msg, {}
            data = json.loads(bytes(value[1:]).decode())
            log.info("🧩 Decoded msg_type=%s, data=%s", msg, data)
            return msg, data
        except Exception as exc:
            log.error("decode error: %s", exc)
            return Msg.ERROR, {"error": str(exc)}

    # ───────────────────── command handlers ---------------------------------
    def _handle_ping(self, data):
        count = data.get("count", 0)
        return self._encode(Msg.PONG, {"count": count})

    def _handle_connect_one(self, data):
        from syncsonic_ble.svc_singleton import service
        from ..flow.connection_service import Intent 
        tgt = data.get("targetSpeaker", {})
        mac = tgt.get("mac")
        if not mac:
            return self._encode(Msg.ERROR, {"error": "Missing targetSpeaker.mac"})

        payload = {
            "mac": mac,
            "friendly_name": tgt.get("name", ""),
            "allowed": data.get("allowed", []),
        }
        log.info("Queuing CONNECT_ONE %s", payload)
        service.submit(Intent.CONNECT_ONE, payload)



        if self.device_manager:
            self.device_manager.connected.add(mac)

        return self._encode(Msg.SUCCESS, {"queued": True})

    def _handle_disconnect(self, data):
        from syncsonic_ble.svc_singleton import service
        from ..flow.connection_service import Intent 
        mac = data.get("mac")
        if not mac:
            return self._encode(Msg.ERROR, {"error": "Missing mac"})
        service.submit(Intent.DISCONNECT, {"mac": mac})
        return self._encode(Msg.SUCCESS, {"queued": True})

    def _handle_set_latency(self, data):
        mac = data.get("mac"); latency = data.get("latency")
        if mac is None or latency is None:
            return self._encode(Msg.ERROR, {"error": "Missing mac/latency"})
        sink_prefix = f"bluez_sink.{mac.replace(':', '_')}"
        ok = create_loopback(sink_prefix, latency_ms=int(latency))
        if ok:
            return self._encode(Msg.SUCCESS, {"latency": latency})
        return self._encode(Msg.ERROR, {"error": "loopback failed"})

    def _handle_set_volume(self, data):
        mac = data.get("mac"); volume = data.get("volume")
        if mac is None or volume is None:
            return self._encode(Msg.ERROR, {"error": "Missing mac/volume"})
        bal = data.get("balance", 0.5)
        ok, left, right = set_stereo_volume(mac, bal, int(volume))
        if ok:
            return self._encode(Msg.SUCCESS, {"left": left, "right": right})
        return self._encode(Msg.ERROR, {"error": "volume failed"})

    def _handle_get_paired(self, _):
        om = dbus.Interface(self.bus.get_object("org.bluez", "/"), DBUS_OM_IFACE)
        paired = {
            v.get("Address"): (v.get("Alias") or v.get("Name"))
            for _, ifs in om.GetManagedObjects().items()
            if (v := ifs.get(DEVICE_INTERFACE)) and v.get("Paired", False)
        }
        return self._encode(Msg.SUCCESS, paired or {"message": "No devices"})

    def _handle_set_mute(self, data):
        mac = data.get("mac"); mute = data.get("mute")
        if mac is None or mute is None:
            return self._encode(Msg.ERROR, {"error": "Missing mac/mute"})
        mac_fmt = mac.replace(":", "_")
        proc = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True)
        if proc.returncode != 0:
            return self._encode(Msg.ERROR, {"error": "Cannot list sinks"})
        sink_name = next((l.split()[1] for l in proc.stdout.splitlines() if mac_fmt in l), None)
        if not sink_name:
            return self._encode(Msg.ERROR, {"error": "sink not found"})
        flag = "1" if mute else "0"
        subprocess.run(["pactl", "set-sink-mute", sink_name, flag], check=True)
        return self._encode(Msg.SUCCESS, {"mac": mac, "mute": mute})

    def _unknown(self, _):
        return self._encode(Msg.ERROR, {"error": "Unknown message"})
    
    def _get_connected_speakers(self):
        """Return a list of {'mac':…, 'alias':…} for every Device1 with Connected=True."""
        om = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, "/"),
            DBUS_OM_IFACE
        )
        devices = []
        for path, ifs in om.GetManagedObjects().items():
            dev = ifs.get(DEVICE_INTERFACE)
            if not dev or not dev.get("Connected", False):
                continue
            devices.append({
                "mac":   dev.get("Address"),
                "alias": dev.get("Alias") or dev.get("Name", "")
            })
        return devices

    def _notify_connected_speakers(self):
        """Push a CONNECTION_STATUS_UPDATE notification with the current speakers."""
        speakers = self._get_connected_speakers()
        log.info("→ [STATUS] notifying %d connected speaker(s)", len(speakers))
        # Use CONNECTION_STATUS_UPDATE for your enum value (0x70)
        self.send_notification(Msg.CONNECTION_STATUS_UPDATE, {"devices": speakers})

    
   
    def _handle_scan_start(self, _):
        """Begin streaming scan: start BlueZ discovery on RESERVED_HCI."""
        # 1) find adapter path & MAC
        hci = os.getenv("RESERVED_HCI")        # e.g. "hci3"
        adapter_path = f"/org/bluez/{hci}"
        try:
            obj = self.bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
            props = dbus.Interface(obj, DBUS_PROP_IFACE)
            adapter_mac = props.Get(ADAPTER_INTERFACE, "Address")
            if self.device_manager:
                log.info("→ [SCAN_START] Found adapter %s (%s)", adapter_path, adapter_mac)
                self._scan_mgr = ScanManager()
                self._scan_mgr.ensure_discovery(adapter_mac)
                self.device_manager.scanning = True
                self._scan_adapter_mac = adapter_mac
        except Exception as e:
            log.error("⚠️ [SCAN_START] Adapter lookup failed: %s", e)
            return self._encode(Msg.ERROR, {"error": "Adapter not found"})
    

        return self._encode(Msg.SUCCESS, {"scanning": True})
    


    def _handle_scan_stop(self, _):
        """Halt streaming scan: stop BlueZ discovery on RESERVED_HCI."""
        if not self._scan_mgr or not self._scan_adapter_mac:
            log.warning("→ [SCAN_STOP] No active scan to stop")
            return self._encode(Msg.ERROR, {"error": "Scan not active"})

        try:
            self._scan_mgr.release_discovery(self._scan_adapter_mac)
            log.info("→ [SCAN_STOP] Discovery stopped on %s", self._scan_adapter_mac)
        except Exception as e:
            log.error("⚠️ [SCAN_STOP] Error stopping discovery: %s", e)
            return self._encode(Msg.ERROR, {"error": "Could not stop scan"})
        
        if self.device_manager:
            self.device_manager.scanning = False
        # clean up
        self._scan_mgr = None
        self._scan_adapter_mac = None

        return self._encode(Msg.SUCCESS, {"scanning": False})


    # ───────────────────── notify start/stop --------------------------------
    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            log.info("Already notifying, ignoring StartNotify")
            return  
        self.notifying = True
        log.info("Notifications enabled via StartNotify")

        self._notify_connected_speakers()
   
      

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        if not self.notifying:
            log.info("Not notifying, ignoring StopNotify")
            return
        self.notifying = False
        log.info("Notifications disabled via StopNotify")

    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed_properties, invalidated_properties):
        pass