# syncsonic_ble/core/descriptors.py

import dbus
import dbus.service
from ..constants import DBUS_PROP_IFACE

class ClientConfigDescriptor(dbus.service.Object):
    UUID = "00002902-0000-1000-8000-00805f9b34fb"

    def __init__(self, bus, index, characteristic):
        self.path = f"{characteristic.get_path()}/desc{index}"
        super().__init__(bus, self.path)
        self.characteristic = characteristic
        # default notifications off
        self.value = [dbus.Byte(0), dbus.Byte(0)]

    @dbus.service.method("org.bluez.GattDescriptor1", in_signature="aya{sv}")
    def WriteValue(self, value, options):
        # [1,0] → on; [0,0] → off
        self.value = value
        on = (len(value) >= 2 and value[0] == 1)
        self.characteristic.notifying = on
        logger = self.characteristic  # or from logging_conf
        logger.info("Notifications %s via CCCD descriptor", "enabled" if on else "disabled")

    @dbus.service.method("org.bluez.GattDescriptor1", out_signature="aya{sv}")
    def ReadValue(self, options):
        return self.value

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if prop == "UUID":
            return dbus.String(self.UUID)
        if prop == "Characteristic":
            return self.characteristic.get_path()
        if prop == "Value":
            return dbus.Array(self.value, signature="y")
        return None

    @dbus.service.method(DBUS_PROP_IFACE, out_signature="a{sv}")
    def GetAll(self):
        return {"UUID": self.UUID,
                "Characteristic": self.characteristic.get_path(),
                "Value": dbus.Array(self.value, signature="y")}
