"""All project‑wide constants & enums live here."""
from enum import IntEnum
import os

# Getting reserved vaiable
reserved = os.getenv("RESERVED_HCI")
if not reserved:
    raise RuntimeError("RESERVED_HCI not set – cannot pick phone adapter")

# D-Bus names / interfaces ---------------------------------------------------
BLUEZ_SERVICE_NAME           = "org.bluez"
DBUS_OM_IFACE                = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE              = "org.freedesktop.DBus.Properties"

# Core adapter/device interfaces
ADAPTER_INTERFACE            = "org.bluez.Adapter1"
DEVICE_INTERFACE             = "org.bluez.Device1"

# GATT registration & runtime interfaces
GATT_MANAGER_IFACE           = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
GATT_SERVICE_IFACE           = "org.bluez.GattService1"
GATT_CHRC_IFACE              = "org.bluez.GattCharacteristic1"

# Agent interfaces
AGENT_INTERFACE              = "org.bluez.Agent1"
AGENT_MANAGER_INTERFACE      = "org.bluez.AgentManager1"
AGENT_MANAGER_IFACE          = "org.bluez.AgentManager1"

# Default agent object path
AGENT_PATH                   = "/com/syncsonic/pair_agent"

# BLE UUIDs ------------------------------------------------------------------
SERVICE_UUID                 = "19b10000-e8f2-537e-4f6c-d104768a1214"
CHARACTERISTIC_UUID          = "19b10001-e8f2-537e-4f6c-d104768a1217"



# Message types – converted to an Enum for type‑safety -----------------------
class Msg(IntEnum):
    PING                    = 0x01
    PONG                    = 0x02
    ERROR                   = 0x03
    SUCCESS                 = 0xF0
    FAILURE                 = 0xF1
    CONNECT_ONE             = 0x60
    DISCONNECT              = 0x61
    SET_LATENCY             = 0x62
    SET_VOLUME              = 0x63
    GET_PAIRED_DEVICES      = 0x64
    SET_MUTE                = 0x65
    CONNECTION_STATUS_UPDATE= 0x70
    SCAN_DEVICES          = 0x40