# endpoints/connect_one.py

from flask import request, jsonify
from pydbus import SystemBus
import time
import re
from endpoints.disconnect import (
    disconnect_device
)
from utils.global_state import *
from utils.pulseaudio_service import create_loopback
from utils.logging import log
from utils.pulseaudio_service import cleanup_pulseaudio, setup_pulseaudio, partial_cleanup_pulseaudio, partial_cleanup_pulseaudio
from utils.bluetooth_helper_functions import _read_line_with_timeout, send_bt_command, bt_select_controller, stop_discovery_all_hcis, pair_device, trust_device, connect_device, remove_device
from endpoints.scan import scan_for_device
from endpoints.setup_box import api_reset_adapters
from endpoints.volume import set_stereo_volume
# Replace with your known controllers if desired
ALL_CONTROLLERS = get_all_controllers()
import subprocess
import time



def connect_one_plan(
    target_mac: str,
    allowed_macs: list[str]
) -> tuple[str, str, list[tuple[str, str]]]:
    target_mac = target_mac.upper()
    allowed_macs = [m.upper() for m in allowed_macs]
    disconnect_list = []
    used_controllers = set()
    target_connected_on = []
    config_speaker_usage = {}

    log(f"🔍 Planning connection for target: {target_mac}")
    log(f"🎯 Allowed MACs in config: {allowed_macs}")

    for ctrl_mac, ctrl_data in GLOBAL_BLUETOOTH_STATE["controllers"].items():
        log(f"🧭 Scanning controller {ctrl_mac} (hci={ctrl_data['hci']})")

        if ctrl_data["hci"] == "hci0":
            log(f"  ↪️ Skipping controller {ctrl_mac} (reserved for phone)")
            continue

        for dev_mac in ctrl_data.get("connected", []):
            dev_mac = dev_mac.upper()
            log(f"    🔗 Found connected device: {dev_mac} on {ctrl_mac}")

            # Track how many controllers each config device is using
            if dev_mac in allowed_macs:
                config_speaker_usage.setdefault(dev_mac, []).append(ctrl_mac)

            # Case 1: Target is already connected
            if dev_mac == target_mac:
                target_connected_on.append(ctrl_mac)
                log(f"    ✅ Target {dev_mac} already connected on {ctrl_mac}")

            # Case 2: Out-of-config speaker (not in config)
            elif dev_mac not in allowed_macs:
                disconnect_list.append((dev_mac, ctrl_mac))
                log(f"    ❌ Out-of-config device {dev_mac} → add to disconnect list")

            # Case 3: Config speaker taking up controller
            elif dev_mac in allowed_macs:
                used_controllers.add(ctrl_mac)
                log(f"    ☑️ Config speaker {dev_mac} occupies controller {ctrl_mac}")

    log(f"📡 Target is currently connected on: {target_connected_on}")
    log(f"🧹 Disconnect list built: {disconnect_list}")
    log(f"🧾 Controllers in use by config devices: {used_controllers}")

    # --- Handle multiple connections of target ---
    if len(target_connected_on) == 1:
        log(f"🟢 Only one controller has the target — no reconnect needed.")
        return "already_connected", target_connected_on[0], disconnect_list

    elif len(target_connected_on) > 1:
        controller_to_keep = target_connected_on[0]
        for ctrl_mac in target_connected_on[1:]:
            disconnect_list.append((target_mac, ctrl_mac))
        log(f"🟡 Target connected on multiple controllers, keeping {controller_to_keep}, disconnecting from others")
        return "already_connected", controller_to_keep, disconnect_list

    # --- No controllers currently hosting the target ---
    # Try to find a truly free one first
    for ctrl_mac, ctrl_data in GLOBAL_BLUETOOTH_STATE["controllers"].items():
        if ctrl_data["hci"] == "hci0":
            continue
        if ctrl_mac not in used_controllers:
            log(f"🔓 Found free controller for connection: {ctrl_mac}")
            return "needs_connection", ctrl_mac, disconnect_list

    # --- All are in use — check for duplicate config speakers ---
    for mac, ctrl_list in config_speaker_usage.items():
        if len(ctrl_list) > 1:
            # Free one controller from this duplicate
            ctrl_to_free = ctrl_list[1]
            disconnect_list.append((mac, ctrl_to_free))
            log(f"🔁 Config speaker {mac} is using multiple controllers — freeing up {ctrl_to_free} for {target_mac}")
            return "needs_connection", ctrl_to_free, disconnect_list

    # Still no options
    log(f"🔴 No available controller found for {target_mac}")
    return "error", "", disconnect_list


def analyze_device_status(controller_mac: str, device_mac: str) -> dict:
    """
    Logs and returns a detailed status report about a device under a given controller.
    Useful for deciding whether to pair, trust, connect, or rediscover.
    """
    controller_mac = controller_mac.upper()
    device_mac = device_mac.upper()

    result = {
        "valid": False,
        "paired": False,
        "connected": False,
        "trusted": False,
        "services_resolved": False,
        "uuids": [],
        "has_audio_profile": False,
        "recommendation": "unknown",
    }

    ctrl = GLOBAL_BLUETOOTH_STATE.get("controllers", {}).get(controller_mac)
    if not ctrl:
        log(f"❌ Controller {controller_mac} not found in global state.")
        result["recommendation"] = "update state"
        return result

    device = ctrl["devices"].get(device_mac)
    if not device:
        log(f"❌ Device {device_mac} not found under controller {controller_mac}.")
        result["recommendation"] = "run discovery"
        return result

    result["valid"] = True
    result["paired"] = device.get("paired", False)
    result["connected"] = device.get("connected", False)
    result["trusted"] = device.get("trusted", False)
    result["services_resolved"] = device.get("services_resolved", False)
    result["uuids"] = device.get("uuids", [])

    # Check if an audio profile is available (A2DP Sink or Headset/Handsfree)
    audio_profiles = ["110b"]
    found_profiles = [uuid for uuid in device["uuids"] if any(ap in uuid.lower() for ap in audio_profiles)]
    result["has_audio_profile"] = len(found_profiles) > 0

    # Logging summary
    log(f"📡 Device {device_mac} under {controller_mac}:")
    log(f"  • Paired: {result['paired']}")
    log(f"  • Connected: {result['connected']}")
    log(f"  • Trusted: {result['trusted']}")
    log(f"  • Services Resolved: {result['services_resolved']}")
    log(f"  • UUIDs: {device['uuids']}")
    log(f"  • Audio Profile Present: {result['has_audio_profile']}")

    # Refined recommendation logic
    if not result["paired"]:
        result["recommendation"] = "pair_and_connect"
    elif not result["trusted"]:
        result["recommendation"] = "trust_and_connect"
    elif not result["has_audio_profile"]:
        result["recommendation"] = "rediscover"
    elif not result["connected"]:
        result["recommendation"] = "connect_only"
    else:
        result["recommendation"] = "already_connected"


    log(f"  → Recommended action: {result['recommendation']}")
    return result



from utils.logging import log

def remove_device_everywhere(mac: str):
    """
    Removes the device with the given MAC address from all available Bluetooth adapters.
    """
    mac = mac.upper().replace(":", "_")
    object_path_fragment = f"dev_{mac}"
    
    bus = SystemBus()
    manager = bus.get("org.bluez", "/")
    objects = manager.GetManagedObjects()

    removed_any = False

    for path, interfaces in objects.items():
        if "org.bluez.Adapter1" in interfaces:
            adapter_path = path
            device_path = f"{adapter_path}/{object_path_fragment}"
            try:
                adapter = bus.get("org.bluez", adapter_path)
                log(f"🗑️ Trying to remove {device_path}")
                adapter.RemoveDevice(device_path)
                log(f"✅ Removed {mac} from {adapter_path}")
                removed_any = True
            except Exception as e:
                log(f"⚠️ Could not remove {mac} from {adapter_path}: {e}")

    if not removed_any:
        log(f"❌ No matching adapters found for {mac}")


def api_connect_one():
    """
    Connect or keep connected exactly one target speaker, while preserving
    other in-config speakers. Remove loopbacks and disconnect out-of-config or duplicate speakers.
    """
    try:
        log("🔄 Resetting Bluetooth adapters...")
        subprocess.run(["/home/syncsonic2/reset_bt_adapters.sh"], check=True)
        log("✅ Bluetooth adapters reset successfully.")
    except subprocess.CalledProcessError as e:
        log(f"❌ Failed to reset Bluetooth adapters: {str(e)}")
        return jsonify({"error": f"Reset script failed: {str(e)}"}), 500
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data"}), 400

    required = required = ["speakers", "settings", "targetSpeaker"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing '{field}'"}), 400

    config_speakers = data["speakers"]
    settings = data["settings"]

    target = data["targetSpeaker"]
    if "mac" not in target or "name" not in target:
        return jsonify({"error": "targetSpeaker missing 'mac' or 'name'"}), 400

    setup_pulseaudio()

    target_mac = target["mac"].upper()
    target_name = target["name"]
    allowed_macs = [m.upper() for m in config_speakers.keys()]

    log("---- /connect-one-in-config ----")
    log(f"Config Speakers: {config_speakers}")
    log(f"Target Speaker: {target_mac} / {target_name}")

    # 1. Refresh the Bluetooth state
    update_bluetooth_state()

    time.sleep(3)

    # 2. Use planner to determine what to do
    status, controller_mac, to_disconnect = connect_one_plan(target_mac, allowed_macs)
    log(f"Status: {status}")
    log(f"Controller MAC: {controller_mac}")
    log(f"Target MAC: {target_mac}")
    log(f"Target Name: {target_name}")
    log(f"Allowed MACs: {allowed_macs}")
    log(f"Controller MAC: {controller_mac}")
    log(f"to disconnect: {to_disconnect}")
    proc = False

    # 3. Disconnect out-of-config or duplicate speakers
    for dev_mac, ctrl_mac in to_disconnect:
        log(f"Disconnecting {dev_mac} from controller {ctrl_mac}")
        disconnect_device(dev_mac, ctrl_mac)
        time.sleep(1)

    success = False

    # 5. Skip connection if target is already connected
    if status == "already_connected":
        success = True
    
    if status == "error":
        return jsonify({"error": "No free controller available"}), 409



    
    if not success:
        subprocess.run(["pkill", "-f", "bluetoothctl"])
        stop_discovery_all_hcis()
        time.sleep(1)
        proc = subprocess.Popen(["bluetoothctl"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True)
        
        
        bt_select_controller(proc, controller_mac)




        
        recommendation = analyze_device_status(controller_mac, target_mac)['recommendation']
        log(f"recommendation: {recommendation}")
        if recommendation == "connect_only":
            log(f"Connecting {target_mac} on {controller_mac}")
            connect_ok = connect_device(proc, target_mac)
            if not connect_ok:
                recommendation = "trust_and_connect"
                log(f"Failed to connect {target_mac} on {controller_mac}, trying trust_and_connect")
            else:
                success = True
        if recommendation == "trust_and_connect":
            log(f"Trusting {target_mac} on {controller_mac}")
            trust_ok = trust_device(proc, target_mac)
            if not trust_ok:
                log(f"Failed to trust {target_mac} on {controller_mac}, trying pair_and_connect")
                
            log(f"Connecting {target_mac} on {controller_mac}")
            connect_ok = connect_device(proc, target_mac)
            if not connect_ok:
                recommendation = "pair_and_connect"
                log(f"Failed to connect {target_mac} on {controller_mac}, trying pair_and_connect")
            else:
                success = True
        if recommendation == "pair_and_connect":
            log(f"Pairing {target_mac} on {controller_mac}")
            pair_ok = pair_device(proc, target_mac)
            if not pair_ok:
                recommendation = "rediscover"
                log(f"Failed to pair {target_mac} on {controller_mac}, trying run discovery")
            else:
                log(f"Trusting {target_mac} on {controller_mac}")
                trust_ok = trust_device(proc, target_mac)
                if not trust_ok:
                    log(f"Failed to trust {target_mac} on {controller_mac}, trying pair_and_connect")
                    
                log(f"Connecting {target_mac} on {controller_mac}")
                connect_ok = connect_device(proc, target_mac)
                if not connect_ok:
                    recommendation = "rediscover"
                    log(f"Failed to connect {target_mac} on {controller_mac}, trying pair_and_connect")
                else:
                        success = True
        if recommendation == "rediscover":
            log(f"removing device {target_mac} from {controller_mac}")
            remove_device(proc, target_mac)
            recommendation = "run discovery"

        if recommendation == "run discovery":
            log(f"scanning {target_mac} on {controller_mac}")
            try:
                found = scan_for_device(proc, target_mac, controller_mac)
            except KeyboardInterrupt:
                print("Scan interrupted by user.")
            if not found:
                if proc:
                    proc.kill()
                return jsonify({"error": f"Failed find {target_mac} on {controller_mac}"}), 400
            else:
                log(f"Pairing {target_mac} on {controller_mac}")
                pair_ok = pair_device(proc, target_mac)
                if not pair_ok:
                    log(f"Failed to pair {target_mac} on {controller_mac}")
                
                log(f"Trusting {target_mac} on {controller_mac}")
                trust_ok = trust_device(proc, target_mac)
                if not trust_ok:
                    success = False
                    log(f"Failed to trust {target_mac} on {controller_mac}, trying pair_and_connect")
                    
                log(f"Connecting {target_mac} on {controller_mac}")
                connect_ok = connect_device(proc, target_mac)
                if not connect_ok:
                    recommendation = "pair_and_connect"
                    log(f"Failed to connect {target_mac} on {controller_mac}, trying pair_and_connect")
                else:
                    success = True

 


    if proc:
        proc.kill()

    # ---- Step 2: If success, handle loopback setup ----
    if success:
        pactl_sink = f"bluez_sink.{target_mac.replace(':','_')}.a2dp_sink"
        speaker_settings = settings.get(target_mac.upper(), {})
        latency = speaker_settings.get("latency", 100)

        if create_loopback(pactl_sink, latency):
            GLOBAL_BLUETOOTH_STATE["loopbacks"][target_mac] = pactl_sink
            log(f"Loopback created for {target_mac} → {pactl_sink}")

            volume = speaker_settings.get("volume")
            balance = speaker_settings.get("balance")
            if volume is not None:
                volume_set, left, right = set_stereo_volume(target_mac, balance, volume)
                log(f"Volume set for {target_mac} → {volume_set}. left: {left}, right: {right}")
                if proc:
                    proc.kill()
                return jsonify({"success": True, "message": f"{target_name} connected and loopback created"}), 200

        else:
            log(f"Could not create loopback for {target_mac}")
            return jsonify({"success": False, "message": "Device connected and but loopback not created"}), 500
    else:

        if proc:
            proc.kill()

        return jsonify({
            "error": "Could not connect. Device removed for clean retry."
            }
        ), 500


