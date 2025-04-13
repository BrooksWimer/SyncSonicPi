from flask import request, jsonify
from pydbus import SystemBus
import glob
from gi.repository import GLib
from utils.bluetooth import (
    get_managed_objects,
    disconnect_device,
    pair_and_connect,
    introspect_paired_and_connected,
    build_connection_gameplan,
    wait_for_property,
    run_connection_plan,
    get_adapter_by_address,
    get_device_by_address,
    get_mac_for_adapter
)
from custom_agent import register_agent
from utils.pulseaudio import setup_pulseaudio, create_loopback, cleanup_pulseaudio
from utils.logging import log
import time

MAX_CONNECT_RETRIES = 3
RETRY_DELAY_SEC = 2



def api_connect():
    # log(reset_all_bluetooth_usb_devices())
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    required_fields = ["configID", "configName", "speakers", "settings"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    speakers = data["speakers"]  # { mac: name }

    try:
        log("---- Starting /connect endpoint ----")
        log("Step 1: Cleaning up PulseAudio...")
        if not cleanup_pulseaudio():
            log("Failed to clean up PulseAudio configuration")
            return jsonify({"error": "Failed to clean up PulseAudio configuration"}), 500
        log("PulseAudio cleanup complete.")

        log("Step 2: Introspecting paired and connected devices...")
        nested_paired, nested_connected = introspect_paired_and_connected()
        log(f"Discovered Paired Devices: {nested_paired}")
        log(f"Discovered Connected Devices: {nested_connected}")

        log("Step 3: Getting system D-Bus and discovering controllers...")
        reserved_mac = get_mac_for_adapter("hci0")
        log(f"🔒 Reserved MAC for hci0: {reserved_mac}")
        bus = SystemBus()
        objects = get_managed_objects(bus)
        controllers = []
        for path, ifaces in objects.items():
            if "org.bluez.Adapter1" in ifaces:
                addr = ifaces["org.bluez.Adapter1"]["Address"]
                if addr == 'B8:27:EB:07:4B:98':
                    continue  # Skip this specific controller
                controllers.append(addr)
        log(f"Discovered controllers: {controllers}")

        log("Step 4: Building gameplan for devices...")
        gameplan = build_connection_gameplan(speakers, controllers, nested_paired, nested_connected)
        log(f"Generated gameplan: {gameplan}")

        log("Step 5: Setting up PulseAudio virtual sink...")
        if not setup_pulseaudio():
            return jsonify({"error": "Failed to set up PulseAudio"}), 500
        log("PulseAudio setup complete.")

        log("Step 6: Running connection plan...")
        run_connection_plan(gameplan)

        # Build connection_status map
        connection_status = {}
        bus = SystemBus()
        objects = get_managed_objects(bus)

        for mac, plan in gameplan.items():
            name = plan["name"]
            ctrl = plan["assigned_controller"]
            adapter_path, _ = get_adapter_by_address(bus, ctrl, objects)
            dev_path, device_obj = get_device_by_address(bus, adapter_path, mac, objects)

            if device_obj and device_obj.Connected:
                connection_status[mac] = {"name": name, "result": "Connected"}
            else:
                connection_status[mac] = {"name": name, "result": "Error in connect"}


        log("Step 8: Creating loopbacks for connected devices...")
        for mac, status in connection_status.items():
            if status["result"] in ["Connected"]:
                mac_str = mac.replace(":", "_")
                sink_name = f"bluez_output.{mac_str}.1"
                log(f"Searching for sink: {sink_name}")
                if create_loopback(sink_name):
                    log(f"Loopback successfully created for {status['name']} → {sink_name}")
                    
                else:
                    log(f"Failed to create loopback for {status['name']} → {sink_name}")
            

        log("Final connection status:")
        for mac, status in connection_status.items():
            log(f"{mac} → {status}")

        return jsonify(connection_status)

    except Exception as e:
        log("Error in /connect endpoint: " + str(e))
        return jsonify({"error": str(e)}), 500


