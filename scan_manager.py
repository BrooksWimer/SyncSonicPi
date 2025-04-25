# scan_manager.py
"""scan_manager
================
Thread‑safe owner of *all* Bluetooth discovery activity.

*   **Exactly one** `StartDiscovery` / `StopDiscovery` call sequence per adapter.
*   Reference count per adapter so multiple callers can share the same scan.
*   Blocking `wait_for_device()` helper that any thread can call.
*   No sleeps: uses `threading.Condition` to wait for BlueZ `InterfacesAdded`
    signals.

The class is transport‑agnostic: Flask, BLE, CLI – anyone can call
`ensure_discovery()` + `wait_for_device()` from any thread.  All BlueZ work is
executed in the *calling* thread, but the internal state is protected by
re‑entrant locks so parallel callers behave correctly.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional
from logging import log
from typing import Any

from bus_manager import get_bus

# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------

class _AdapterEntry:
    __slots__ = ("proxy", "refcount")

    def __init__(self, proxy: Any):
        self.proxy: Any = proxy
        self.refcount: int = 0

# ---------------------------------------------------------------------------
# Public ScanManager
# ---------------------------------------------------------------------------

class ScanManager:
    """Serialises discovery on every adapter.

    Typical usage by connection logic::

        scan_mgr = ScanManager()           # usually one global instance
        scan_mgr.ensure_discovery(ctrl)
        path = scan_mgr.wait_for_device(ctrl, mac, 20)
        scan_mgr.release_discovery(ctrl)
    """

    # -----------------------------
    # Construction / BlueZ setup
    # -----------------------------

    def __init__(self):
        self._bus = get_bus()
        self._adapters: Dict[str, _AdapterEntry] = {}   # mac → entry
        self._lock = threading.RLock()                  # guards adapters & maps
        self._cond = threading.Condition(self._lock)    # signalled on device add

        # Subscribe once to BlueZ InterfacesAdded signals.
        self._bus.subscribe(
            iface="org.freedesktop.DBus.ObjectManager",
            signal="InterfacesAdded",
            signal_fired=self._on_interfaces_added,
        )

        # Build initial adapter map.
        self._refresh_adapters()

    # -----------------------------
    # Public discovery control
    # -----------------------------

    def ensure_discovery(self, adapter_mac: str) -> None:
        """Increment ref‑count; start discovery if it was previously idle."""
        adapter_mac = adapter_mac.upper()
        with self._lock:
            entry = self._adapters.get(adapter_mac)
            if not entry:
                raise ValueError(f"Adapter {adapter_mac} not found in BlueZ")

            if entry.refcount == 0:
                try:
                    entry.proxy.StartDiscovery()
                except Exception as e:  # noqa: BLE001
                    if "InProgress" not in str(e):
                        raise
            entry.refcount += 1

    def release_discovery(self, adapter_mac: str) -> None:
        """Decrement ref‑count; stop discovery when it reaches 0."""
        adapter_mac = adapter_mac.upper()
        with self._lock:
            entry = self._adapters.get(adapter_mac)
            if not entry:
                return
            if entry.refcount == 0:
                return  # programming error, but ignore
            entry.refcount -= 1
            if entry.refcount == 0:
                try:
                    entry.proxy.StopDiscovery()
                except Exception as e:  # noqa: BLE001
                    if "InProgress" in str(e):
                        log("[ScanMgr] StopDiscovery ignored (BlueZ busy)")
                    else:
                        raise 
    def wait_for_device(
        self,
        adapter_mac: str,
        target_mac: str,
        timeout_s: int = 20,
    ) -> Optional[str]:
        """Block until *target_mac* is discovered on *adapter_mac*.

        Returns the D‑Bus object path on success; **None** on timeout.
        """
        adapter_mac = adapter_mac.upper()
        target_mac = target_mac.upper()
        deadline = time.time() + timeout_s

        with self._cond:
            # Fast‑path: maybe it is already in the object tree
            path = self._lookup_device_path(adapter_mac, target_mac)
            if path:
                return path

            # Wait until InterfacesAdded arrives or timeout.
            while time.time() < deadline:
                remaining = deadline - time.time()
                self._cond.wait(timeout=remaining)
                path = self._lookup_device_path(adapter_mac, target_mac)
                if path:
                    return path
        return None

    # -----------------------------
    # BlueZ signal handler
    # -----------------------------

    def _on_interfaces_added(self, sender, object_path, *args, **kwargs):  # noqa: D401,E501  # pragma: no cover
        # We don’t care about the details; just wake up waiters.
        with self._cond:
            self._cond.notify_all()

    # -----------------------------
    # Internal helpers
    # -----------------------------

    def _refresh_adapters(self):
        """Populate the adapters dict from current BlueZ object tree."""
        om = self._bus.get("org.bluez", "/")
        objects = om.GetManagedObjects()
        for path, ifaces in objects.items():
            if "org.bluez.Adapter1" in ifaces:
                mac = ifaces["org.bluez.Adapter1"].get("Address", "").upper()
                if mac not in self._adapters:
                    proxy = self._bus.get("org.bluez", path)
                    self._adapters[mac] = _AdapterEntry(proxy)

    def _lookup_device_path(self, adapter_mac: str, dev_mac: str) -> Optional[str]:
        """Return device object path if it exists under *adapter_mac*."""
        om = self._bus.get("org.bluez", "/")
        objects = om.GetManagedObjects()
        dev_mac_fmt = dev_mac.replace(":", "_")
        for path, ifaces in objects.items():
            if "org.bluez.Device1" in ifaces and path.endswith(dev_mac_fmt):
                if path.startswith(self._adapters[adapter_mac].proxy._path):  # type: ignore[attr-defined]  # noqa: SLF001
                    return path
        return None

    def refresh_adapters(self) -> None:
        """
        Rebuild the internal adapter map after the USB-reset script has
        detached/re-attached the dongles.  Call this once, right after the
        reset, before any new ensure_discovery() request.
        """
        with self._lock:
            self._adapters.clear()      # forget everything we knew
            self._refresh_adapters()    # repopulate from BlueZ