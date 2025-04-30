# bus_manager.py
"""bus_manager
===============
Thread‑safe **singleton** accessor for the system D‑Bus.

*   Uses **pydbus.SystemBus()** (same API you already call elsewhere).
*   Creates the connection once; afterwards every thread gets the exact same
    object.
*   No asyncio, no extra dependencies – drop‑in for the existing synchronous
    codebase.

Usage
-----
```python
from bus_manager import get_bus
bus = get_bus()              # safe in any thread
```
The connection lives until the Python interpreter exits; BlueZ cleans up the
socket automatically, so you don’t need an explicit shutdown.
"""

from __future__ import annotations

import threading
from typing import Optional

from pydbus import SystemBus

# ---------------------------------------------------------------------------
# Internal synchronisation primitives
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()          # guards first‑time creation
_BUS: Optional[SystemBus] = None  # the singleton instance


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_bus() -> SystemBus:
    """Return the process‑wide :class:`pydbus.SystemBus`.

    Calling this function from multiple threads is safe; the first caller wins
    the creation race, everyone else immediately reuses the same connection.
    """
    global _BUS

    if _BUS is None:
        # Fast path failed – only then pay the cost of locking.
        with _LOCK:
            # Double‑checked locking pattern: another thread may have created
            # the bus while we were waiting for the lock.
            if _BUS is None:
                _BUS = SystemBus()
    return _BUS
