from flask import request, jsonify
from pydbus import SystemBus
import glob
from utils.logging import log
from utils.pulseaudio import create_loopback, cleanup_pulseaudio, setup_pulseaudio
from utils.bluetooth import (
    get_managed_objects,
    disconnect_device,
    pair_and_connect,
    introspect_paired_and_connected,
    build_connection_gameplan,
    get_mac_for_adapter
)

def api_pair():
    data = request.get_json()
    if not data or "devices" not in data:
        return jsonify({"error": "Missing 'devices' field in JSON body"}), 400

    devices = data["devices"]  # format: { "MAC": "Device Name", ... }

    try:
        log("---- Starting /pair endpoint ----")

        log("Step 1: Cleaning up PulseAudio...")
        if not cleanup_pulseaudio():
            log("Failed to clean up PulseAudio")
            return jsonify({"error": "Failed to clean up PulseAudio"}), 500
        log("PulseAudio cleanup complete.")

        log("Step 2: Introspecting paired and connected devices...")
        nested_paired, nested_connected = introspect_paired_and_connected()
        log(f"Discovered Paired Devices: {nested_paired}")
        log(f"Discovered Connected Devices: {nested_connected}")

        log("Step 3: Discovering Bluetooth controllers via D-Bus...")
        reserved_mac = get_mac_for_adapter("hci0")
        bus = SystemBus()
        objects = get_managed_objects(bus)
        controllers = [
            ifaces["org.bluez.Adapter1"]["Address"]
            for path, ifaces in objects.items()
            if "org.bluez.Adapter1" in ifaces and ifaces["org.bluez.Adapter1"]["Address"] != 'B8:27:EB:07:4B:98'
        ]
        log(f"Discovered controllers: {controllers}")

        log("Step 4: Building connection gameplan...")
        gameplan = build_connection_gameplan(devices, controllers, nested_paired, nested_connected)
        log(f"Generated gameplan: {gameplan}")

        log("Step 5: Setting up PulseAudio virtual sink...")
        if not setup_pulseaudio():
            return jsonify({"error": "Failed to set up PulseAudio"}), 500
        log("PulseAudio setup complete.")

        log("Step 6: Running connection plan...")
        from utils.bluetooth import run_connection_plan  # Ensure it's imported
        connection_status = run_connection_plan(gameplan)

        log("Step 7: Creating loopbacks for connected devices...")
        for mac, status in connection_status.items():
            if status["result"] == "Connected":
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
        log("Error in /pair endpoint: " + str(e))
        return jsonify({"error": str(e)}), 500

