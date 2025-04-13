from flask import Flask, jsonify, request
from pydbus import SystemBus
import threading
import subprocess
import queue
import re
import time
import json
import signal
import os

# Import from utils
from utils.logging import log, RED, GREEN, YELLOW, BLUE, HEADER, BOLD, ENDC
from utils.pulseaudio import setup_pulseaudio, cleanup_pulseaudio, create_loopback
from utils.bluetooth import (
    get_managed_objects,
    get_adapter_by_address,
    get_device_by_address,
    disconnect_device,
    pair_and_connect
)

# Import individual endpoints
from endpoints.connect import api_connect
from endpoints.pair import api_pair
from endpoints.disconnect import api_disconnect
from endpoints.volume import api_volume
from endpoints.latency import api_latency
from endpoints.paired_devices import api_paired_devices
from endpoints.connect_phone import api_connect_phone
from endpoints.setup_box import api_reset_adapters
from endpoints.scan import (
    api_start_scan,
    api_stop_scan,
    api_device_queue,
    api_scan_status
)

app = Flask(__name__)

# Register routes
app.add_url_rule("/connect", view_func=api_connect, methods=["POST"])
app.add_url_rule("/pair", view_func=api_pair, methods=["POST"])
app.add_url_rule("/disconnect", view_func=api_disconnect, methods=["POST"])
app.add_url_rule("/volume", view_func=api_volume, methods=["POST"])
app.add_url_rule("/latency", view_func=api_latency, methods=["POST"])
app.add_url_rule("/paired-devices", view_func=api_paired_devices, methods=["GET"])
app.add_url_rule("/connect_phone", view_func=api_connect_phone, methods=["POST"])
app.add_url_rule("/reset-adapters", view_func=api_reset_adapters, methods=["POST"])


# Register scanning routes
app.add_url_rule("/start-scan", view_func=api_start_scan, methods=["GET"])
app.add_url_rule("/stop-scan", view_func=api_stop_scan, methods=["GET"])
app.add_url_rule("/device-queue", view_func=api_device_queue, methods=["GET"])
app.add_url_rule("/scan-status", view_func=api_scan_status, methods=["GET"])

# Add debug logging for route registration
log(f"Registered routes:")
log(f"- POST /connect")
log(f"- POST /pair")
log(f"- POST /disconnect")
log(f"- POST /volume")
log(f"- POST /latency")
log(f"- GET /paired-devices")
log(f"- GET /start-scan")
log(f"- GET /stop-scan")
log(f"- GET /scan-status")
log(f"- GET /device-queue")
log(f"- POST /connect_phone")
log(f"- POST /reset-adapters")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, threaded=True) 