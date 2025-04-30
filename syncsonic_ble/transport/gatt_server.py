# syncsonic_ble/transport/gatt_server.py

import sys
import os
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import signal
from ..constants import (
    BLUEZ_SERVICE_NAME,
    SERVICE_UUID,
    CHARACTERISTIC_UUID,
    GATT_MANAGER_IFACE,
    LE_ADVERTISING_MANAGER_IFACE,
    AGENT_MANAGER_INTERFACE,
    AGENT_PATH,
    reserved
)
from ..logging_conf import get_logger
from ..core.adapters import find_adapter, set_bus
from ..core.agent import PhonePairingAgent, CAPABILITY
from ..core.device_manager import DeviceManager
from ..core.characteristic import Characteristic
from ..core.service import GattService, Application
from ..core.advertisement import Advertisement
from utils.pulseaudio_service import setup_pulseaudio
from ..core.descriptors import ClientConfigDescriptor

log = get_logger(__name__)

def get_ad_manager_for_reserved(bus):
    """
    Grab the LEAdvertisingManager1 interface on the adapter named by $RESERVED_HCI
    and log the adapter path for verification.
    """
    reserved = os.getenv("RESERVED_HCI")
    if not reserved:
        raise RuntimeError("RESERVED_HCI not set – cannot pick phone adapter")
    adapter_path = f"/org/bluez/{reserved}"
    log.info("🔧 RESERVED_HCI env variable: %s", reserved)
    obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
    ad_mgr = dbus.Interface(obj, LE_ADVERTISING_MANAGER_IFACE)
    log.info("🌐 Advertising manager interface acquired on %s", adapter_path)
    return ad_mgr


def main():
    # 1) Audio setup
    setup_pulseaudio()

    # 2) D-Bus GLib integration
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    set_bus(bus)

    # 3) Adapter selection
    adapter_path, adapter = find_adapter(reserved)
    if not adapter_path:
        log.error("No Bluetooth adapter found – aborting")
        sys.exit(1)
    log.info("🎛️  Using primary adapter: %s", adapter_path)

    # 4) Pairing agent registration
    agent = PhonePairingAgent(bus, AGENT_PATH)
    agent_mgr = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez"),
        AGENT_MANAGER_INTERFACE
    )
    agent_mgr.RegisterAgent(AGENT_PATH, CAPABILITY)
    agent_mgr.RequestDefaultAgent(AGENT_PATH)
    log.info("🤝 Phone pairing agent registered at %s", AGENT_PATH)

    # 5) DeviceManager + GATT service/characteristic
    dev_mgr = DeviceManager(bus, adapter_path)
    svc = GattService(bus, 0, SERVICE_UUID, primary=True)
    char = Characteristic(bus, 0, CHARACTERISTIC_UUID,['read', 'write', 'write-without-response', 'notify'], svc)
    svc.add_characteristic(char)
    dev_mgr.attach_characteristic(char)
    char.device_manager = dev_mgr
    cccd = ClientConfigDescriptor(bus, 0, char)
    # If your Characteristic class tracks descriptors, append it there:
    if hasattr(char, 'descriptors'):
        char.descriptors.append(cccd)

    # 6) Application tree assembly
    app = Application(bus)
    app.add_service(svc)

    # 7) Register GATT _and_ Advertisement on the reserved adapter
    gatt_mgr = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        GATT_MANAGER_IFACE
    )
    ad_mgr = get_ad_manager_for_reserved(bus)
    adv = Advertisement(bus, 0)
    # Log advertisement details
    log.info("📢 Preparing to advertise service UUID %s with name '%s'", SERVICE_UUID, adv.local_name if hasattr(adv, 'local_name') else 'N/A')

    gatt_mgr.RegisterApplication(
        app.get_path(), {},
        reply_handler=lambda: log.info("✅ GATT application registered on %s", adapter_path),
        error_handler=lambda e: log.error("GATT error on %s: %s", adapter_path, e)
    )
    ad_mgr.RegisterAdvertisement(
        adv.get_path(), {},
        reply_handler=lambda: log.info("✅ Advertisement registered on adapter %s", os.getenv('RESERVED_HCI')),
        error_handler=lambda e: log.error("Advertisement error on adapter %s: %s", os.getenv('RESERVED_HCI'), e)
    )

    
    log.info('BLE GATT server running...')
    log.info(f'Using adapter: {adapter_path}')
    log.info('Device name: Sync-Sonic')
    log.info('Service UUID: %s', SERVICE_UUID)
    log.info('Characteristic UUID: %s', CHARACTERISTIC_UUID)
    log.info('Pairing enabled - accepting secure connections')
    log.info('Waiting for connections...')

    # Spin up the GLib loop in a local variable
    loop = GLib.MainLoop()
    log.info("🚀 SyncSonic BLE server ready – advertisements running on %s", os.getenv('RESERVED_HCI'))

    try:
        loop.run()
    except KeyboardInterrupt:
        log.info("🛑 Server stopped by user (KeyboardInterrupt)")
    except Exception as e:
        log.error(f"⚠️ Unexpected server error: {e}")


