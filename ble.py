#!/usr/bin/env python3

import sys, json, logging
import dbus, dbus.mainloop.glib, dbus.service
from gi.repository import GLib
from svc_singleton import service
from connection_service import Intent
import subprocess
from utils.pulseaudio_service import create_loopback, remove_loopback_for_device, setup_pulseaudio
from endpoints.volume import set_stereo_volume
from phone_connection_agent import PhonePairingAgent, CAPABILITY
import os

# Getting reserved vaiable
reserved = os.getenv("RESERVED_HCI")
if not reserved:
    raise RuntimeError("RESERVED_HCI not set – cannot pick phone adapter")

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
AGENT_INTERFACE = 'org.bluez.Agent1'
AGENT_MANAGER_INTERFACE = 'org.bluez.AgentManager1'
ADAPTER_INTERFACE = 'org.bluez.Adapter1'
DEVICE_INTERFACE = 'org.bluez.Device1'
AGENT_PATH = "/com/syncsonic/pair_agent"

_launched_classic = False
# Message types
MESSAGE_TYPES = {
    "PING": 0x01,
    "PONG": 0x02,
    "ERROR": 0x03,
    "SUCCESS": 0xF0,
    "FAILURE": 0xF1,
    "CONNECT_ONE":  0x60,
    "DISCONNECT":0x61,
    "SET_LATENCY":0x62,
    "SET_VOLUME":0x63,
    "GET_PAIRED_DEVICES":0x64,
    "SET_MUTE":0x65,

}

# UUIDs from specification
SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214'
CHARACTERISTIC_UUID = '19b10001-e8f2-537e-4f6c-d104768a1217'

mainloop = None


def find_adapter(bus, preferred_adapter=None):
    """
    Find and return the first available Bluetooth adapter or a specific one if preferred_adapter is set.

    Args:
        bus: The D-Bus system bus
        preferred_adapter: Optional name of preferred adapter (e.g., 'hci0')

    Returns:
        Tuple of (adapter_path, adapter_interface) or (None, None) if no adapter found
    """
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'), DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()

    for path, interfaces in objects.items():
        if ADAPTER_INTERFACE not in interfaces:
            continue

        if preferred_adapter:
            adapter_name = path.split('/')[-1]
            if adapter_name == preferred_adapter:
                adapter = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, path), ADAPTER_INTERFACE)
                return path, adapter
        else:
            adapter = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, path), ADAPTER_INTERFACE)
            return path, adapter

    return None, None


def reset_adapter(adapter):
    """
    Reset the Bluetooth adapter to a clean state.
    """
    try:
        # Get the adapter properties interface
        adapter_props = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter.object_path),
            DBUS_PROP_IFACE)

        # Power cycle the adapter
        adapter_props.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(False))
        GLib.timeout_add(2000, lambda: None)  # Longer delay to ensure power down
        adapter_props.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(True))

        # # Remove all devices
        # objects = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'), DBUS_OM_IFACE).GetManagedObjects()
        # for path, interfaces in objects.items():
        #     if 'org.bluez.Device1' in interfaces:
        #         device = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, path), 'org.bluez.Device1')
        #         device_props = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, path), DBUS_PROP_IFACE)
        #         try:
        #             # Remove trusted status and disconnect
        #             device_props.Set('org.bluez.Device1', 'Trusted', dbus.Boolean(False))
        #             device.Disconnect()
        #         except:
        #             pass
        #         try:
        #             adapter.RemoveDevice(dbus.ObjectPath(path))
        #         except:
        #             pass

        # # Wait a bit after cleaning up devices
        GLib.timeout_add(1000, lambda: None)

        logger.info("Adapter reset successfully")
    except Exception as e:
        logger.error(f"Failed to reset adapter: {e}")


class DeviceManager:
    def __init__(self, bus, adapter_path):
        self.bus = bus
        self.adapter_path = adapter_path
        self.devices = {}
        self.reconnect_attempts = {}
        self.max_reconnect_attempts = 3
        self.pairing_in_progress = set()
        self.setup_device_monitoring()
        self._status = {}          # mac → {"path": <dbus>, "alias": str, "connected": bool}
        self._char   = None        # will hold a ref to the GATT characteristic
        self.connected = set()
     

    @staticmethod
    def _extract_mac(path: str) -> str | None:
        if "dev_" not in path:
            return None
        return path.split("/")[-1].replace("dev_", "").replace("_", ":").upper()
    

    def _devices_on_adapter(self, adapter_prefix):
        """Return a list of MACs for devices currently Connected under that adapter."""
        om  = self.bus.get_object(BLUEZ_SERVICE_NAME, "/")
        mgr = dbus.Interface(om, DBUS_OM_IFACE)
        objs = mgr.GetManagedObjects()

        connected = []
        for obj_path, ifaces in objs.items():
            dev = ifaces.get("org.bluez.Device1")
            if not dev or not dev.get("Connected", False):
                continue
            # path is like /org/bluez/hciX/dev_XX_YY_…
            if obj_path.startswith(adapter_prefix):
                connected.append(dev["Address"])
        return connected

    # called once from main() after you instantiate Characteristic
    def attach_characteristic(self, char):
        self._char = char

    # helper that recomputes full status & notifies
    def _publish(self):
        if not self._char:
            return
        payload = {"connected": list(self.connected)}
        self._char.push_status(payload) 

    def _update_status(self, mac: str, connected: bool, alias: str):
        self._status[mac] = {
            "alias": alias,
            "connected": connected
        }
        logger.info(f"[STATUS] {mac} → {'✓ connected' if connected else '✗ disconnected'}")
        self._publish()

    def setup_device_monitoring(self):
        obj = self.bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
        self.bus.add_signal_receiver(
            self.interfaces_added,
            dbus_interface='org.freedesktop.DBus.ObjectManager',
            signal_name='InterfacesAdded')

        self.bus.add_signal_receiver(
            self.properties_changed,
            dbus_interface='org.freedesktop.DBus.Properties',
            signal_name='PropertiesChanged',
            path_keyword='path')

    def reset_device_state(self, path, remove_device=True):
        """Reset all state for a device"""
        self.pairing_in_progress.discard(path)
        if path in self.reconnect_attempts:
            self.reconnect_attempts[path] = 0

        if remove_device and path in self.devices:
            try:
                # Remove device from adapter
                adapter = dbus.Interface(
                    self.bus.get_object(BLUEZ_SERVICE_NAME, self.adapter_path),
                    ADAPTER_INTERFACE
                )
                adapter.RemoveDevice(dbus.ObjectPath(path))
                del self.devices[path]
                logger.info(f"Reset device state and removed device: {path}")
            except Exception as e:
                logger.error(f"Failed to remove device: {e}")
        else:
            logger.info(f"Reset device state (keeping device): {path}")


    def interfaces_added(self, path, interfaces):
        if DEVICE_INTERFACE in interfaces:
            self.device_found(path)

    def properties_changed(self, interface, changed, invalidated, path):
        # logger.info(f"[DeviceManager] PropertiesChanged: iface={interface}, path={path}, changed={changed}")
        global _launched_classic
        if interface != DEVICE_INTERFACE:
            return

        
        if interface == DEVICE_INTERFACE and 'Connected' in changed:
        
            connected = bool(changed['Connected'])
            mac       = self._extract_mac(path)         # guaranteed by first-seen block
            logger.info(f"[BlueZ] {mac} is now "
                f"{'✓ CONNECTED' if connected else '✗ DISCONNECTED'}")
            

            if connected:

                # --- NEW connection -------------------------------------------------
                if mac not in self.connected:
                    dev_obj   = self.bus.get_object(BLUEZ_SERVICE_NAME, path)
                    dev_props = dbus.Interface(dev_obj, DBUS_PROP_IFACE)

                    adapter_prefix = "/".join(path.split("/")[:4])

                    # dynamic check instead of your dict:
                    existing = self._devices_on_adapter(adapter_prefix)
                    others = [m for m in existing if m != mac]
                    if others:
                            # somebody’s already using that adapter
                            dev_iface = dbus.Interface(dev_obj, DEVICE_INTERFACE)
                            dev_iface.Disconnect()
                            logger.warning(
                                f"{mac} tried to connect on {adapter_prefix}, "
                                f"but {others[0]} is already using it. "
                                "Click connect to find an open port."
                            )
                            return

                    # 1) Only speakers with A2DP in their UUID list
                    try:
                        uuids = dev_props.Get(DEVICE_INTERFACE, "UUIDs")
                    except Exception:
                        uuids = []
                    if not any("110b" in u.lower() for u in uuids):
                        logger.info(f"{mac} has no A2DP UUIDs, skipping")
                        return

                    # 2) Check if BlueZ already has a MediaTransport1 for this device
                    om  = self.bus.get_object(BLUEZ_SERVICE_NAME, "/")
                    mgr = dbus.Interface(om, DBUS_OM_IFACE)
                    objs = mgr.GetManagedObjects()
                    fmt = mac.replace(":", "_")
                    has_transport = any(
                        "org.bluez.MediaTransport1" in ifaces and fmt in path
                        for path, ifaces in objs.items()
                    )

                    # 3) If no transport yet, trigger profile connect
                    dev_iface = dbus.Interface(dev_obj, DEVICE_INTERFACE)
                    if not has_transport:
                        try:
                            dev_iface.ConnectProfile("0000110b-0000-1000-8000-00805f9b34fb")
                            logger.info(f"Triggered A2DP connect for {mac}")
                        except Exception as e:
                            logger.error(f"Failed ConnectProfile on {mac}: {e}")

                    sink_name = f"bluez_sink.{fmt}.a2dp_sink"
                    # 5) Finally create the loopback
                    self.connected.add(mac)
                    create_loopback(sink_name)
                    logger.info(f"Created loopback for {mac}")

            else:
                # --- DISCONNECTION ---------------------------------------------------
                if mac in self.connected:
                    self.connected.remove(mac)
                    remove_loopback_for_device(mac)
                    logger.info(f"{mac} disconnected – now {len(self.connected)} left")


            self._update_status(mac, connected, changed.get('Alias', mac))  
            
        

        if path in self.devices:
            dev_props = self.devices[path]['props']

            # Handle pairing state changes
            if 'Paired' in changed:
                if changed['Paired']:
                    logger.info(f"Device paired successfully: {path}")
        


                else:
                    logger.info(f"Device unpaired: {path}")
    


               
            

    def device_found(self, path):
        if path in self.devices:
            return

        try:
            device = self.bus.get_object(BLUEZ_SERVICE_NAME, path)
            device_props = dbus.Interface(device, DBUS_PROP_IFACE)
            device_iface = dbus.Interface(device, DEVICE_INTERFACE)

            # Store the device
            self.devices[path] = {
                'device': device,
                'props': device_props,
                'iface': device_iface
            }

            try:
                # Set trusted and blocked properties
                device_props.Set(DEVICE_INTERFACE, 'Trusted', dbus.Boolean(True))
                device_props.Set(DEVICE_INTERFACE, 'Blocked', dbus.Boolean(False))
            except Exception as e:
                logger.debug(f"Could not set device properties: {e}")

            logger.info(f"New device registered: {path}")

        
        except Exception as e:
            logger.error(f"Failed to register device {path}: {e}")


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.service = service
        self.value = [dbus.Byte(0)] * 5
        self.notifying = False
        self.connected_devices = set()
        self.device_manager = None
        self.scanning = False
        self.scan_process = None
        dbus.service.Object.__init__(self, bus, self.path)
        logger.info(f"Characteristic created with UUID: {uuid}")

    def notify_connected(self, macs: list[str]):
        self.value = self.encode_response(MESSAGE_TYPES["SUCCESS"],
                                        {"connected": macs})
        if self.notifying:
            self.PropertiesChanged(GATT_CHRC_IFACE,
                                {'Value': dbus.Array(self.value)}, [])
            
    def push_status(self, payload: dict):
        """
        Encode *payload* as JSON and fire a notification.
        Example payload the phone will receive:
            {
              "connected": ["AA:BB:…", "11:22:…"],
              "playback":  {"AA:BB:…": {"latency": 120}, ...}
            }

        """
        logger.debug(f"[PUSH]   {json.dumps(payload)}")

        self.value = self.encode_response(MESSAGE_TYPES["SUCCESS"], payload)
        if self.notifying:                            # only if the phone wrote CCCD
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {'Value': dbus.Array(self.value)},    # new value
                []                                    # no invalidated props
            )

    def set_device_manager(self, device_manager):
        self.device_manager = device_manager

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Value': self.value,
                'Notifying': dbus.Boolean(self.notifying)
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def handle_device_connection(self, device_path, connected):
        if connected:
            self.connected_devices.add(device_path)
            if self.device_manager:
                self.device_manager.device_found(device_path)
            logger.info(f"Device connected: {device_path}")
        else:
            self.connected_devices.discard(device_path)
            logger.info(f"Device disconnected: {device_path}")

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='ss',
                         out_signature='v')
    def Get(self, interface, prop):
        if prop == "Value":
            logger.debug(f"Get value called: {self.value}")
            return dbus.Array(self.value, signature='y')
        return None

    def encode_response(self, message_type, data):
        """Encode a response message"""
        try:
            json_str = json.dumps(data)
            json_bytes = json_str.encode('utf-8')
            response = [dbus.Byte(message_type)]
            response.extend([dbus.Byte(b) for b in json_bytes])
            return response
        except Exception as e:
            logger.error(f"Error encoding response: {e}")
            return self.encode_response(MESSAGE_TYPES["ERROR"], {"error": str(e)})

    def decode_message(self, value):
        """Decode a received message"""
        try:
            message_type = value[0]
            if len(value) > 1:
                json_bytes = bytes([int(b) for b in value[1:]])
                data = json.loads(json_bytes.decode('utf-8'))
            else:
                data = {}
            return message_type, data
        except Exception as e:
            logger.error(f"Error decoding message: {e}")
            return MESSAGE_TYPES["ERROR"], {"error": str(e)}




 
    def handle_connect(self, data):
        """
        CONNECT_ONE – expect:
            {
            "targetSpeaker": { "mac": "AA:BB:CC:DD:EE:FF", "name": "Friendly" },
            "settings": { "AA:BB:...": {...}, … },
            "allowed": [ "AA:BB:CC:DD:EE:FF", ... ]
            }
        """
        try:
            tgt = data["targetSpeaker"]
            payload = {
                "mac":           tgt["mac"],
                "friendly_name": tgt.get("name", ""),
                "allowed":       data.get("allowed", []),
            }
            service.submit(Intent.CONNECT_ONE, payload)
            return self.encode_response(MESSAGE_TYPES["SUCCESS"],
                                        {"queued": True})
        except Exception as e:
            return self.encode_response(MESSAGE_TYPES["ERROR"],
                                        {"error": str(e)})





    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
     
        """Handle incoming messages"""
        # logger.debug(f"WriteValue called with value: {value}, options: {options}")
        # logger.debug(f"=== Backend WriteValue Debug ===")
        # logger.debug(f"Raw value received: {value}")
        # logger.debug(f"Value as hex: {[hex(b) for b in value]}")
        # logger.debug(f"Value as bytes: {[b for b in value]}")
        # logger.debug(f"Options: {options}")


        # Check if this is a CCCD write (notification enable/disable)
        if len(value) == 2 and value[0] == 0x01:  # CCCD write
            self.cccd_value = value
            if value[1] == 0x01:  # Enable notifications
                self.notifying = True
                logger.info("Notifications enabled via CCCD")
            else:  # Disable notifications
                self.notifying = False
                logger.info("Notifications disabled via CCCD")
    

        # Handle device connection
        device = options.get('device', None)
        if device:
            self.handle_device_connection(device, True)

        try:
            message_type, data = self.decode_message(value)

            # Handle different message types
            if message_type == MESSAGE_TYPES["PING"]:
                response = [dbus.Byte(MESSAGE_TYPES["PONG"])]
                response.extend([dbus.Byte(b) for b in data.get("count", 0).to_bytes(4, byteorder='big')])
            elif message_type == MESSAGE_TYPES["CONNECT_ONE"]:
                response = self.handle_connect_one(data)
            elif message_type == MESSAGE_TYPES["DISCONNECT"]:
                response = self.handle_disconnect(data)
            elif message_type == MESSAGE_TYPES["SET_LATENCY"]:
                response = self.handle_set_latency(data)
            elif message_type == MESSAGE_TYPES["SET_VOLUME"]:
                response = self.handle_set_volume(data)
            elif message_type == MESSAGE_TYPES["GET_PAIRED_DEVICES"]:
                response = self.handle_get_paired_devices(data)
            elif message_type == MESSAGE_TYPES["SET_MUTE"]:
                response = self.handle_set_mute(data)
            else:
                response = self.encode_response(MESSAGE_TYPES["ERROR"],
                                             {"error": "Unknown message type"})

            # Set response and notify if needed
            self.value = response
            if device in self.connected_devices and self.notifying:
                self.PropertiesChanged(GATT_CHRC_IFACE, {'Value': dbus.Array(self.value)}, [])

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.value = self.encode_response(MESSAGE_TYPES["ERROR"], {"error": str(e)})
            if device in self.connected_devices and self.notifying:
                self.PropertiesChanged(GATT_CHRC_IFACE, {'Value': dbus.Array(self.value)}, [])

    def handle_connect_one(self, data):
        """
        CONNECT_ONE — expected payload
        {
            "targetSpeaker": { "mac": "AA:BB:CC:DD:EE:FF", "name": "Kitchen JBL" },
            "settings": { "AA:BB:…": {...}, … }
        }
        Queues an Intent.CONNECT_ONE job for the background ConnectionService.
        """
        try:
            tgt = data.get("targetSpeaker")
            if not tgt or "mac" not in tgt:
                return self.encode_response(
                    MESSAGE_TYPES["ERROR"],
                    {"error": "Missing targetSpeaker.mac"}
                )

            payload = {
                "mac":           tgt["mac"],
                "friendly_name": tgt.get("name", ""),
                "allowed":       data.get("allowed", []),
            }

            logging.info(f"handle_connect_one: {payload}")

            if self.device_manager:
                self.device_manager.connected.add(tgt["mac"])
            
            # Push the work item to the singleton service queue
            service.submit(Intent.CONNECT_ONE, payload)


            return self.encode_response(
                MESSAGE_TYPES["SUCCESS"],
                {"queued": True}
            )
        except Exception as e:
            logger.error(f"handle_connect_one: {e}")
            if self.device_manager:
                self.device_manager.connected.discard(tgt["mac"])
            
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": str(e)}
            )
        
    def handle_disconnect(self, data):
        """
        DISCONNECT_ONE — expected payload:
        { "mac": "AA:BB:CC:DD:EE:FF" }
        Queues an Intent.DISCONNECT job for the background ConnectionService.
        """
        try:
            mac = data.get("mac")
            if not mac:
                return self.encode_response(
                    MESSAGE_TYPES["ERROR"],
                    {"error": "Missing mac"}
                )

            # Push the work item to the singleton service queue
            service.submit(Intent.DISCONNECT, {"mac": mac})

            return self.encode_response(
                MESSAGE_TYPES["SUCCESS"],
                {"queued": True}
            )

        except Exception as e:
            logger.error(f"handle_disconnect_one: {e}")
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": str(e)}
            )
        


    def handle_set_latency(self, data):
        """
        SET_LATENCY — expected payload:
          { "mac": "AA:BB:CC:DD:EE:FF", "latency": 100 }
        """
        # Validate input
        mac = data.get("mac")
        latency = data.get("latency")
        if not mac or latency is None:
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": "Missing 'mac' or 'latency'"}
            )

        try:
            # Exactly your existing loopback logic:
            mac_fmt = mac.replace(":", "_")
            sink_prefix = f"bluez_sink.{mac_fmt}"
            # create_loopback is in your pulseaudio_service module
            success = create_loopback(sink_prefix, latency_ms=latency)

            if success:
                return self.encode_response(
                    MESSAGE_TYPES["SUCCESS"],
                    {"message": f"Latency for {mac} set to {latency} ms"}
                )
            else:
                return self.encode_response(
                    MESSAGE_TYPES["ERROR"],
                    {"error": f"Failed to create loopback for {mac}"}
                )

        except Exception as e:
            logger.error(f"handle_set_latency: {e}")
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": str(e)}
            )
        
    def handle_set_volume(self, data):
        mac     = data.get("mac")
        volume  = data.get("volume")
        balance = data.get("balance", 0.5)

        if mac is None or volume is None:
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": "Missing 'mac' or 'volume'"}
            )

        try:
            success, left, right = set_stereo_volume(mac, balance, int(volume))

            if success:
                return self.encode_response(
                    MESSAGE_TYPES["SUCCESS"],
                    {
                      "mac": mac,
                      "left": left,
                      "right": right
                    }
                )
            else:
                return self.encode_response(
                    MESSAGE_TYPES["ERROR"],
                    {"error": f"Failed to set volume for {mac}"}
                )

        except Exception as e:
            logger.error(f"handle_set_volume: {e}")
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": str(e)}
            )
        

    def handle_get_paired_devices(self, data):
        om = dbus.Interface(
            self.bus.get_object("org.bluez", "/"),
            "org.freedesktop.DBus.ObjectManager"
        )
        objects = om.GetManagedObjects()

        devices = {}
        for path, ifaces in objects.items():
            dev = ifaces.get("org.bluez.Device1")
            if not dev or not dev.get("Paired", False):
                continue
            mac  = dev.get("Address")
            name = dev.get("Alias") or dev.get("Name") or mac
            devices[mac] = name

        if not devices:
            return self.encode_response(
                MESSAGE_TYPES["SUCCESS"],
                {"message": "No devices are paired."}
            )
        return self.encode_response(
            MESSAGE_TYPES["SUCCESS"],
            devices
        )
    
    
    def handle_set_mute(self, data):
        """
        SET_MUTE — payload:
          { "mac": "AA:BB:CC:DD:EE:FF", "mute": true }
        """
        mac  = data.get("mac")
        mute = data.get("mute")

        if mac is None or mute is None:
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": "Missing 'mac' or 'mute'"}
            )

        try:
            # list sinks
            proc = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True, text=True
            )
            if proc.returncode != 0:
                err = proc.stderr.strip()
                logger.error(f"Error getting sink list: {err}")
                return self.encode_response(
                    MESSAGE_TYPES["ERROR"],
                    {"error": "Failed to get sink list"}
                )

            # find the sink matching this MAC
            mac_fmt = mac.replace(":", "_")
            sink_name = None
            for line in proc.stdout.splitlines():
                if mac_fmt in line:
                    sink_name = line.split()[1]
                    break

            if not sink_name:
                return self.encode_response(
                    MESSAGE_TYPES["ERROR"],
                    {"error": f"No sink found for device {mac}"}
                )

            # mute or unmute
            flag = "1" if mute else "0"
            subprocess.run(
                ["pactl", "set-sink-mute", sink_name, flag],
                check=True
            )
            action = "Muted" if mute else "Unmuted"
            logger.info(f"{action} speaker {mac} ({sink_name})")

            return self.encode_response(
                MESSAGE_TYPES["SUCCESS"],
                {"mac": mac, "mute": mute}
            )

        except subprocess.CalledProcessError as e:
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": f"Command failed: {e}"}
            )
        except Exception as e:
            logger.error(f"handle_set_mute: {e}")
            return self.encode_response(
                MESSAGE_TYPES["ERROR"],
                {"error": str(e)}
            )
        
    

    



    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        if self.notifying:
            logger.info("Already notifying, ignoring StartNotify")
            return
        self.notifying = True
        logger.info("Notifications enabled via StartNotify")
   
      

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        if not self.notifying:
            logger.info("Not notifying, ignoring StopNotify")
            return
        self.notifying = False
        logger.info("Notifications disabled via StopNotify")

    @dbus.service.signal(DBUS_PROP_IFACE,
                        signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed_properties, invalidated_properties):
        pass

class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = 'peripheral'  # Changed from advertising_type to always be 'peripheral'
        self.service_uuids = [SERVICE_UUID]
        self.local_name = 'Sync-Sonic'
        self.include_tx_power = True
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.discoverable = True
        self.pairing      = False 
        dbus.service.Object.__init__(self, bus, self.path)
        logger.info("Advertisement created")

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        props = {
            'org.bluez.LEAdvertisement1': {
                'Type': dbus.String(self.ad_type),
                'ServiceUUIDs': dbus.Array(self.service_uuids, signature='s'),
                'LocalName': dbus.String(self.local_name),
                'IncludeTxPower': dbus.Boolean(self.include_tx_power),
                'Discoverable': dbus.Boolean(self.discoverable),
                # 'Pairing': dbus.Boolean(self.pairing)
            }
        }
        return props

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='ss',
                         out_signature='v')
    def Get(self, interface, prop):
        return self.get_properties()['org.bluez.LEAdvertisement1'][prop]

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        return self.get_properties()['org.bluez.LEAdvertisement1']

    @dbus.service.method('org.bluez.LEAdvertisement1', in_signature='', out_signature='')
    def Release(self):
        logger.info("Advertisement released")

class Service(dbus.service.Object):
    def __init__(self, bus, index, uuid, primary):
        self.path = '/org/bluez/example/service' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)
        logger.info(f"Service created with UUID: {uuid}")

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    [c.get_path() for c in self.characteristics],
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)
        logger.debug(f"Added characteristic to service: {characteristic.uuid}")

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        logger.info("Application created")

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_OM_IFACE,
                         out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.characteristics:
                response[chrc.get_path()] = chrc.get_properties()
        return response

    def add_service(self, service):
        self.services.append(service)
        logger.debug(f"Added service to application: {service.uuid}")

def main():
    global mainloop
    global bus

    logger.info("Setting up pulseaudio...")
    setup_pulseaudio()

    logger.info("Starting BLE server...")

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # Find the Bluetooth adapter (prefer hci1)
    adapter_path, adapter = find_adapter(bus, reserved)
    if not adapter_path:
        logger.error("No Bluetooth adapter found")
        sys.exit(1)

    logger.info(f"Using Bluetooth adapter: {adapter_path}")

    

    # Create device manager
    device_manager = DeviceManager(bus, adapter_path)

    # reset_adapter(adapter)

 
    agent = PhonePairingAgent(bus, AGENT_PATH)  
    # Create and register the agent
    agent_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, '/org/bluez'),
        AGENT_MANAGER_INTERFACE
    )

    try:
        agent_manager.RegisterAgent(AGENT_PATH, CAPABILITY)
        agent_manager.RequestDefaultAgent(AGENT_PATH)
        logger.info("Agent registered")
    except Exception as e:
        logger.error(f"Failed to register agent: {e}")
        sys.exit(1)

    # Set adapter properties
    adapter_props = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        DBUS_PROP_IFACE
    )

    try:
        # Make sure adapter is powered on
        adapter_props.Set(ADAPTER_INTERFACE, 'Powered', dbus.Boolean(True))

        # Configure adapter properties for pairing
        adapter_props.Set(ADAPTER_INTERFACE, 'Pairable', dbus.Boolean(True))
        adapter_props.Set(ADAPTER_INTERFACE, 'PairableTimeout', dbus.UInt32(0))
        adapter_props.Set(ADAPTER_INTERFACE, 'Discoverable', dbus.Boolean(True))
        adapter_props.Set(ADAPTER_INTERFACE, 'DiscoverableTimeout', dbus.UInt32(0))

        # Set adapter name
        adapter_props.Set(ADAPTER_INTERFACE, 'Alias', dbus.String('Sync-Sonic'))

        logger.info("Adapter properties set successfully")
    except Exception as e:
        logger.error(f"Failed to set adapter properties: {e}")
        sys.exit(1)

    # Create the GATT service and characteristic
    service = Service(bus, 0, SERVICE_UUID, True)
    char = Characteristic(bus, 0, CHARACTERISTIC_UUID, ['read', 'write', 'write-without-response', 'notify'], service)
    char.set_device_manager(device_manager)
    service.add_characteristic(char)

    device_manager.attach_characteristic(char)  

    # Create the GATT application
    app = Application(bus)
    app.add_service(service)

    # Register the GATT application
    service_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        GATT_MANAGER_IFACE
    )

    # Register the advertisement
    ad_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        LE_ADVERTISING_MANAGER_IFACE
    )
    ad = Advertisement(bus, 0, 'peripheral')

    mainloop = GLib.MainLoop()

    try:
        service_manager.RegisterApplication(app.get_path(), {},
            reply_handler=lambda: logger.info('GATT application registered'),
            error_handler=lambda e: logger.error(f'Failed to register application: {e}')
        )

        ad_manager.RegisterAdvertisement(ad.get_path(), {},
            reply_handler=lambda: logger.info('Advertisement registered'),
            error_handler=lambda e: logger.error(f'Failed to register advertisement: {e}')
        )
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        sys.exit(1)

    logger.info('BLE GATT server running...')
    logger.info(f'Using adapter: {adapter_path}')
    logger.info('Device name: Sync-Sonic')
    logger.info('Service UUID: %s', SERVICE_UUID)
    logger.info('Characteristic UUID: %s', CHARACTERISTIC_UUID)
    logger.info('Pairing enabled - accepting secure connections')
    logger.info('Waiting for connections...')

    try:
        mainloop.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")

if __name__ == '__main__':
    main()