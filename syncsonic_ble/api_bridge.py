"""Tiny glue layer – turn validated dicts into ConnectionService intents."""
from typing import Any
from .constants import Msg
from logging_conf import get_logger
from syncsonic_ble.flow.connection_service import Intent, service   # existing singleton

log = get_logger(__name__)

def _submit(intent: Intent, payload: dict[str, Any]):
    log.info("Queueing %s %s", intent, payload)
    service.submit(intent, payload)
    return {"queued": True}

# ─── public helpers used by Characteristic ──────────────────────────────────

def queue_connect_one(data):
    tgt = data.get("targetSpeaker", {})
    return _submit(Intent.CONNECT_ONE, {
        "mac":           tgt.get("mac"),
        "friendly_name": tgt.get("name", ""),
        "allowed":       data.get("allowed", []),
    })

def queue_disconnect(data):
    return _submit(Intent.DISCONNECT, {"mac": data.get("mac")})

def queue_set_latency(data):
    return _submit(Intent.SET_LATENCY, data)

def queue_set_volume(data):
    return _submit(Intent.SET_VOLUME, data)

def queue_set_mute(data):
    return _submit(Intent.SET_MUTE, data)