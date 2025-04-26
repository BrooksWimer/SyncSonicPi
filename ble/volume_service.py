# ble/volume_service.py
from __future__ import annotations
from typing import Any
import json

from svc_singleton import service
from connection_service import Intent

# ─────────────────────────────────────────────
# UUID constants
# ─────────────────────────────────────────────
SRV_UUID   = "d8282b50-274e-4e5e-9b5c-e6c2cddd0000"
CONN_UUID  = "d8282b50-274e-4e5e-9b5c-e6c2cddd0002"
DISC_UUID  = "d8282b50-274e-4e5e-9b5c-e6c2cddd0003"

# ─────────────────────────────────────────────
#  Connect ONE characteristic
# ─────────────────────────────────────────────
class ConnectCharacteristic:
    PATH = "/syncsonic/service0/char0"
    _props = {
        "org.bluez.GattCharacteristic1": {
            "UUID":   CONN_UUID,
            "Service": "/syncsonic/service0",
            "Flags":  ["write-without-response", "write"],
        }
    }
    _interfaces = ["org.bluez.GattCharacteristic1"]

    def WriteValue(self, value: list[int], options: dict[str, Any]):  # noqa: N802
        try:
            data = json.loads(bytes(value).decode("utf-8"))
            target  = data["targetSpeaker"]
            payload = {
                "mac":           target["mac"],
                "friendly_name": target.get("name", ""),
                "allowed":       list(data.get("settings", {}).keys()),
            }
            service.submit(Intent.CONNECT_ONE, payload)
            print(f"✅ CONNECT_ONE queued for {payload['mac']}")
        except Exception as exc:
            print("ConnectCharacteristic error:", exc)
            raise

# ─────────────────────────────────────────────
#  Disconnect characteristic
# ─────────────────────────────────────────────
class DisconnectCharacteristic:
    PATH = "/syncsonic/service0/char1"
    _props = {
        "org.bluez.GattCharacteristic1": {
            "UUID":   DISC_UUID,
            "Service": "/syncsonic/service0",
            "Flags":  ["write-without-response", "write"],
        }
    }
    _interfaces = ["org.bluez.GattCharacteristic1"]

    def WriteValue(self, value: list[int], options: dict[str, Any]):  # noqa: N802
        try:
            mac = json.loads(bytes(value).decode("utf-8"))["mac"]
            service.submit(Intent.DISCONNECT, {"mac": mac})
            print(f"✅ DISCONNECT queued for {mac}")
        except Exception as exc:
            print("DisconnectCharacteristic error:", exc)
            raise

# ─────────────────────────────────────────────
#  GATT Service container
# ─────────────────────────────────────────────
class BleService:
    PATH = "/syncsonic/service0"
    _props = {
        "org.bluez.GattService1": {
            "UUID":    SRV_UUID,
            "Primary": True,
        }
    }
    _interfaces = ["org.bluez.GattService1"]

    def __init__(self):
        self.char_connect    = ConnectCharacteristic()
        self.char_disconnect = DisconnectCharacteristic()

# ─────────────────────────────────────────────
#  Registration helper
# ─────────────────────────────────────────────
def register_ble_tree() -> None:
    bus = service.bus

    srv = BleService()

    # 3-argument form: (path, interfaces|props, python_object)
    bus.register_object(srv.PATH,                srv._interfaces,          srv)
    bus.register_object(srv.char_connect.PATH,   srv.char_connect._interfaces,
                        srv.char_connect)
    bus.register_object(srv.char_disconnect.PATH, srv.char_disconnect._interfaces,
                        srv.char_disconnect)

    adapter  = bus.get("org.bluez", "/org/bluez/hci0")
    gatt_mgr = adapter["org.bluez.GattManager1"]
    gatt_mgr.RegisterApplication(
        "/syncsonic",
        {},
        reply_handler=lambda: print("✅ GATT app registered"),
        error_handler=lambda e: print("❌ GATT register failed:", e),
    )
