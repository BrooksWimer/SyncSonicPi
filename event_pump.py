# event_pump.py
import threading
from gi.repository import GLib
from bus_manager import get_bus
from utils.logging import log

def start_event_pump():
    """Start GLib MainLoop in a background thread exactly once."""
    def _runner():
        log("🌀 GLib event loop running")
        loop = GLib.MainLoop()
        loop.run()

    # Singleton pattern so multiple imports don't spawn extra threads.
    if not getattr(start_event_pump, "_started", False):
        bus = get_bus()  # Touching the bus forces pydbus to initialise GLib
        threading.Thread(target=_runner, daemon=True).start()
        start_event_pump._started = True
