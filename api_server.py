from flask import Flask

# Import individual endpoints
from custom_bt_agent import api_disconnect, api_connect_one
from endpoints.volume import api_volume, api_mute
from endpoints.latency import api_latency
from endpoints.paired_devices import api_paired_devices
from endpoints.connect_phone import api_connect_phone
from endpoints.setup_box import api_reset_adapters
# from endpoints.connect_one_speaker import api_connect_one
from endpoints.scan import (
    api_start_scan,
    api_stop_scan,
    api_device_queue,
    api_scan_status
)
from utils.global_state import api_get_connected_devices

app = Flask(__name__)

# Register routes
app.add_url_rule("/disconnect", view_func=api_disconnect, methods=["POST"])
app.add_url_rule("/volume", view_func=api_volume, methods=["POST"])
app.add_url_rule("/latency", view_func=api_latency, methods=["POST"])
app.add_url_rule("/paired-devices", view_func=api_paired_devices, methods=["GET"])
app.add_url_rule("/connect_phone", view_func=api_connect_phone, methods=["POST"])
app.add_url_rule("/reset-adapters", view_func=api_reset_adapters, methods=["POST"])
app.add_url_rule("/connect-one", view_func=api_connect_one, methods=["POST"])
app.add_url_rule("/connected-devices", view_func=api_get_connected_devices, methods=["GET"])
app.add_url_rule("/mute", view_func=api_mute, methods=["POST"])


# Register scanning routes
app.add_url_rule("/start-scan", view_func=api_start_scan, methods=["GET"])
app.add_url_rule("/stop-scan", view_func=api_stop_scan, methods=["GET"])
app.add_url_rule("/device-queue", view_func=api_device_queue, methods=["GET"])
app.add_url_rule("/scan-status", view_func=api_scan_status, methods=["GET"])



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, threaded=True) 