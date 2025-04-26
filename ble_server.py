from event_pump import start_event_pump
from svc_singleton import service                # spawns ConnectionService
from connection_service import Intent
# ---------------------------------------------------------------
from dbus.mainloop.glib import DBusGMainLoop
import dbus, dbus.service, json
from gi.repository import GLib

BLUEZ   = "org.bluez"
SRV_UUID   = "d8282b50-274e-4e5e-9b5c-e6c2cddd0000"
CONN_UUID  = "d8282b50-274e-4e5e-9b5c-e6c2cddd0002"
DISC_UUID  = "d8282b50-274e-4e5e-9b5c-e6c2cddd0003"
DBusGMainLoop(set_as_default=True)         
dbus_bus = dbus.SystemBus()            
# === Mini GATT objects in-lined right here =====================
class _BaseChar(dbus.service.Object):
    FLAGS = dbus.Array(["write-without-response", "write"], signature="s")
    def __init__(self, bus, path, uuid):
        self.bus  = bus
        self.path = path
        self.uuid = uuid
        super().__init__(bus, path)

    @dbus.service.method("org.freedesktop.DBus.Properties",
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return {
            "UUID":     self.uuid,
            "Service":  dbus.ObjectPath("/syncsonic/service0"),
            "Flags":    self.FLAGS
        } if iface == "org.bluez.GattCharacteristic1" else {}

    @dbus.service.method("org.bluez.GattCharacteristic1",
                         in_signature="aya{sv}", out_signature="")
    def WriteValue(self, value, opts):
        self._handle(bytes(value))

    def _handle(self, raw: bytes): ...

class ConnectChar(_BaseChar):
    def _handle(self, raw):
        data = json.loads(raw.decode())
        target = data["targetSpeaker"]
        payload = {
            "mac":           target["mac"],
            "friendly_name": target.get("name",""),
            "allowed":       list(data.get("settings",{}).keys())
        }
        service.submit(Intent.CONNECT_ONE, payload)
        print("✅ CONNECT_ONE queued", payload["mac"])

class DisconnectChar(_BaseChar):
    def _handle(self, raw):
        mac = json.loads(raw.decode())["mac"]
        service.submit(Intent.DISCONNECT, {"mac": mac})
        print("✅ DISCONNECT queued", mac)

class BleService(dbus.service.Object):
    PATH = "/syncsonic/service0"
    def __init__(self, bus):
        super().__init__(bus, self.PATH)
        self.conn = ConnectChar(bus, self.PATH+"/char0", CONN_UUID)
        self.disc = DisconnectChar(bus, self.PATH+"/char1", DISC_UUID)

    @dbus.service.method("org.freedesktop.DBus.Properties",
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        if iface != "org.bluez.GattService1": return {}
        return {
            "UUID":     SRV_UUID,
            "Primary":  dbus.Boolean(True),
            "Characteristics": dbus.Array(
                [self.conn.path, self.disc.path], signature="o")
        }

def _register_connect_only_gatt():
    bus = dbus_bus                                 # ← dbus-python bus
    srv = BleService(bus)                          # dbus.service.Object expects this

    # find hci0 on *dbus-python* bus
    om = dbus.Interface(bus.get_object(BLUEZ, "/"),
                        "org.freedesktop.DBus.ObjectManager")
    adapter_path = next(path for path, ifaces in om.GetManagedObjects().items()
                        if "org.bluez.Adapter1" in ifaces and path.endswith("hci0"))

    gatt_mgr = dbus.Interface(bus.get_object(BLUEZ, adapter_path),
                              "org.bluez.GattManager1")
    gatt_mgr.RegisterApplication(srv.PATH, {},
        reply_handler=lambda: print("✅ BLE GATT registered"),
        error_handler=lambda e: print("❌ BLE GATT error:", e))

# ── launch everything ──────────────────────────────────────────
if __name__ == "__main__":
    print("ConnectionService worker thread started")  # you already see this

    _register_connect_only_gatt()     # <<<  NEW

    start_event_pump()                # GLib loop in background
    GLib.MainLoop().run()             # keep main thread alive
