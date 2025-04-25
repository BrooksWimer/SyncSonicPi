from gi.repository import GLib
from utils.logging import log
import time
from utils.pulseaudio_service import remove_loopback_for_device

def get_adapter_path_from_device(device_path: str) -> str:
    return "/".join(device_path.split("/")[:4])


def connect_device_dbus(device_path: str, bus) -> bool:
    try:
        device = bus.get("org.bluez", device_path)
        log(f"Connecting to device at {device_path}")
        device.Connect()
        return True
    except Exception as e:
        log(f"Failed to connect at {device_path}: {e}")
        return False


def trust_device_dbus(device_path: str, bus) -> bool:
    try:
        device = bus.get("org.bluez", device_path)
        log(f"Setting Trusted=true for device at {device_path}")
        device.Trusted = True
        return True
    except Exception as e:
        log(f"Failed to trust device at {device_path}: {e}")
        return False


def pair_device_dbus(device_path: str, bus) -> bool:
    try:
        time.sleep(1.5)
        device = bus.get("org.bluez", device_path)
        log(f"Pairing device at {device_path}")
        device.Pair()
        return True
    except Exception as e:
        log(f"Failed to pair device at {device_path}: {e}")
        return False


def remove_device_dbus(device_path: str, bus) -> bool:
    adapter_path = get_adapter_path_from_device(device_path)
    try:
        adapter = bus.get("org.bluez", adapter_path)
        log(f"Removing device at {device_path} from adapter {adapter_path}")
        adapter.RemoveDevice(device_path)
        return True
    except Exception as e:
        log(f"Failed to remove device at {device_path}: {e}")
        return False



def disconnect_device_dbus(device_path: str, mac: str, bus) -> bool:
    """
    Disconnects the specified Bluetooth device using its full D-Bus path.
    """
    try:
        device = bus.get("org.bluez", device_path)
        log(f"Attempting disconnect of {mac} at {device_path}")
        device.Disconnect()
        remove_loopback_for_device(mac)
        log(f"Successfully disconnected {mac} at {device_path}")
        return True
    except Exception as e:
        log(f"Failed to disconnect {mac} at {device_path}: {e}")
        return False
    

def disconnect_all_instances(mac: str, objects: dict, bus) -> bool:
    """
    Disconnects the given device from all controllers where it is currently connected.
    Uses the full D-Bus object tree instead of any global state.
    """
    mac = mac.upper()
    mac_fmt = mac.replace(":", "_")
    attempted = False

    for path, ifaces in objects.items():
        if "org.bluez.Device1" in ifaces:
            dev = ifaces["org.bluez.Device1"]
            address = dev.get("Address", "").upper()
            connected = dev.get("Connected", False)
            if address == mac and connected:
                try:
                    device = bus.get("org.bluez", path)
                    log(f"Attempting to disconnect {mac} at {path}")
                    device.Disconnect()
                    remove_loopback_for_device(mac)
                    log(f"Successfully disconnected {mac} at {path}")
                    attempted = True
                except Exception as e:
                    log(f"Failed to disconnect {mac} at {path}: {e}")

    if not attempted:
        log(f"No active connections found for {mac} in managed objects")
    return attempted
