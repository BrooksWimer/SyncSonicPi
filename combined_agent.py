import logging
import dbus


# ── Logging Setup ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-7s %(message)s"
)
logger = logging.getLogger(__name__)

AGENT_PATH = '/com/syncsonic/agent'
CAPABILITY  = 'DisplayYesNo'  # works for both classic & LE

class CombinedAgent(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, AGENT_PATH)
        logger.info(f"CombinedAgent initialized at {AGENT_PATH}")

    # ——— org.bluez.Agent1 methods ———

    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Release(self):
        logger.info("Agent.Release()")

    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        logger.info(f"AuthorizeService: device={device} uuid={uuid}")
        # always allow your custom GATT service

    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        logger.info(f"RequestConfirmation: device={device} passkey={passkey}")
        # user sees “yes/no” prompt

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        logger.info(f"RequestPinCode: device={device}")
        return '0000'  # or your default

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        logger.info(f"RequestPasskey: device={device}")
        return dbus.UInt32(0)

    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def DisplayPasskey(self, device, passkey):
        logger.info(f"DisplayPasskey: device={device}, passkey={passkey}")

    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def DisplayPinCode(self, device, pincode):
        logger.info(f"DisplayPinCode: device={device}, pincode={pincode}")

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        logger.info(f"RequestAuthorization: device={device}")

    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Cancel(self):
        logger.info("Agent.Cancel()")
