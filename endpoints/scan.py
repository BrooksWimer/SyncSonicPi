from flask import jsonify
import threading
import queue
import subprocess
import time
import re
from utils.logging import log

# Global state
scanning = False
scan_process = None
device_queue = queue.Queue()
seen_devices = {}  # Track seen devices

def api_start_scan():
    global scanning, scan_process
    if scanning:
        return jsonify({"message": "Already scanning."}), 200
    scanning = True
    threading.Thread(target=scan_devices_background, daemon=True).start()
    return jsonify({"message": "Scan started."}), 200

def api_stop_scan():
    global scanning, scan_process
    scanning = False
    try:
        if scan_process and scan_process.stdin:
            scan_process.stdin.write("scan off\n")
            scan_process.stdin.flush()
            time.sleep(1)
            scan_process.kill()
            scan_process = None
            log("Scan stopped and bluetoothctl process killed.")
    except Exception as e:
        log(f"Error in /stop-scan: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Scanning stopped."})

def api_device_queue():
    global seen_devices
    while not device_queue.empty():
        mac, name = device_queue.get()
        seen_devices[mac] = name
    return jsonify(seen_devices)

def api_scan_status():
    return jsonify({
        "scanning": scanning,
        "process_running": scan_process is not None,
        "device_count": len(seen_devices)
    })

def scan_devices_background():
    global scanning, scan_process
    log("scan_devices_background thread started")

    scan_process = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    # Initialize bluetoothctl
    scan_process.stdin.write("power on\n")
    scan_process.stdin.write("agent on\n")
    scan_process.stdin.write("default-agent\n")
    scan_process.stdin.write("scan on\n")
    scan_process.stdin.flush()
    log("Sent 'scan on' to bluetoothctl")

    try:
        while scanning:
            line = scan_process.stdout.readline()
            log(f"bluetoothctl output: {line.strip()}")
            
            if "NEW" in line:
                parts = line.strip().split()
                if len(parts) >= 4:
                    mac = parts[2]
                    display_name = " ".join(parts[3:])
                    if re.search(r'([0-9A-F]{2}-){2,}', display_name, re.IGNORECASE):
                        log(f"Filtering out device: {display_name}")
                    else:
                        device_queue.put((mac, display_name))
                        log(f"Adding device: {mac} with name: {display_name}")
    except Exception as e:
        log(f"Scan error: {e}")
    finally:
        scanning = False
        if scan_process and scan_process.stdin:
            scan_process.stdin.write("scan off\n")
            scan_process.stdin.flush()
        