import dbus.service
from ..constants import LE_ADVERTISING_MANAGER_IFACE, SERVICE_UUID
from ..logging_conf import get_logger

log = get_logger(__name__)

class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, advertising_type='peripheral'):
        self.path            = self.PATH_BASE + str(index)
        self.bus             = bus
        self.ad_type         = advertising_type
        self.service_uuids   = [SERVICE_UUID]
        self.local_name      = 'Sync-Sonic'
        self.include_tx_power= True
        self.discoverable    = True
        super().__init__(bus, self.path)
        log.info(f"Advertisement created at {self.path}")

    def get_path(self) -> dbus.ObjectPath:
        """Return this advertisement’s D-Bus object path."""
        return dbus.ObjectPath(self.path)

    def get_properties(self) -> dict:
        return {
            'org.bluez.LEAdvertisement1': {
                'Type':           dbus.String(self.ad_type),
                'ServiceUUIDs':   dbus.Array(self.service_uuids, signature='s'),
                'LocalName':      dbus.String(self.local_name),
                'IncludeTxPower': dbus.Boolean(self.include_tx_power),
                'Discoverable':   dbus.Boolean(self.discoverable),
            }
        }

    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        return self.get_properties()['org.bluez.LEAdvertisement1'][prop]

    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.get_properties()['org.bluez.LEAdvertisement1']

    @dbus.service.method('org.bluez.LEAdvertisement1', in_signature='', out_signature='')
    def Release(self):
        log.info("Advertisement released")
