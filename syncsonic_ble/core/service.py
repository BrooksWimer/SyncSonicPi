from __future__ import annotations
import dbus
from ..constants import GATT_SERVICE_IFACE, DBUS_OM_IFACE, DBUS_PROP_IFACE
from ..logging_conf import get_logger

log = get_logger(__name__)

class GattService(dbus.service.Object):
    """A single GATT service, exposing its characteristics."""

    def __init__(self, bus, index: int, uuid: str, primary: bool = True):
        # e.g. "/org/bluez/example/service0"
        self.path            = f"/org/bluez/example/service{index}"
        self.bus             = bus
        self.uuid            = uuid
        self.primary         = primary
        self.characteristics = []
        super().__init__(bus, self.path)
        log.info(f"GattService created at {self.path} (UUID={uuid})")

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, ch: dbus.service.Object) -> None:
        self.characteristics.append(ch)

    def get_properties(self) -> dict:
        # Returns the org.bluez.GattService1 properties dict
        char_paths = dbus.Array([c.get_path() for c in self.characteristics],
                                signature="o")
        return {
            GATT_SERVICE_IFACE: {
                "UUID":        self.uuid,
                "Primary":     dbus.Boolean(self.primary),
                "Characteristics": char_paths,
            }
        }

    # Expose properties via org.freedesktop.DBus.Properties
    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature="ss", out_signature="v")
    def Get(self, interface: str, prop: str) -> "v":
        return self.get_properties()[interface][prop]

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str) -> dict:
        return self.get_properties()[interface]
    
    

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/com/syncsonic/app'
        self.services = []
        super().__init__(bus, self.path)

    def add_service(self, service):
        self.services.append(service)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        reply: dict[str, dict] = {}

        for svc in self.services:
            # 1) service node
            reply[svc.get_path()] = svc.get_properties()

            for chrc in svc.characteristics:
                # 2) characteristic node
                reply[chrc.get_path()] = chrc.get_properties()

                # 3) any descriptors under that characteristic
                for desc in getattr(chrc, 'descriptors', []):
                    reply[desc.get_path()] = desc.get_properties()

        return reply
