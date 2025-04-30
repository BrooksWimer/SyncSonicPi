# syncsonic_ble/core/agent.py

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

from ..constants import AGENT_INTERFACE, AGENT_PATH
from ..logging_conf import get_logger

log = get_logger(__name__)

# Capability for DisplayYesNo pairing
CAPABILITY = "DisplayYesNo"

class PhonePairingAgent(dbus.service.Object):
    """BlueZ Agent1 implementation to handle pairing requests."""

    def __init__(self, bus, path: str = AGENT_PATH):
        super().__init__(bus, path)
        log.info(f"Agent initialized at {path}")

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        log.info("Agent.Release() called")

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device: str, uuid: str):
        log.info(f"Agent.AuthorizeService(device={device}, uuid={uuid}) called")

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device: str, passkey: int):
        log.info(f"Agent.RequestConfirmation(device={device}, passkey={passkey}) called")

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device: str) -> str:
        log.info(f"Agent.RequestPinCode(device={device}) called")
        return "0000"

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device: str) -> int:
        log.info(f"Agent.RequestPasskey(device={device}) called")
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def DisplayPasskey(self, device: str, passkey: int):
        log.info(f"Agent.DisplayPasskey(device={device}, passkey={passkey}) called")

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device: str, pincode: str):
        log.info(f"Agent.DisplayPinCode(device={device}, pincode={pincode}) called")

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device: str):
        log.info(f"Agent.RequestAuthorization(device={device}) called")

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        log.info("Agent.Cancel() called")
