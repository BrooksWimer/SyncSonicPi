from flask import jsonify
import threading
import queue
import subprocess
import time
import re
from utils.logging import log
from utils.bluetooth_helper_functions import send_bt_command, _read_line_with_timeout

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
        


def scan_for_device(proc, target_mac: str, target_port: str, scan_timeout: int = 30) -> bool:
    """
    Scans for a Bluetooth device with the specified MAC using a bluetoothctl subprocess.
    Returns True if the device is found, otherwise False after timeout.
    """
    import re
    import time

    target_mac = target_mac.upper().replace("-", ":")
    print(f"[SCAN] Looking for MAC {target_mac} on port {target_port} for {scan_timeout}s...")
    time.sleep(3)

    # Try to start scanning, handle 'InProgress' errors
    print("[SCAN] ▶️ Starting scan...")
    send_bt_command(proc, "scan on")
    time.sleep(0.5)

    for _ in range(5):  # Read a few lines to check for scan errors
        line = _read_line_with_timeout(proc, 1)
        if not line:
            continue
        print(f"[SCAN] Output: {line.strip()}")
        if "org.bluez.Error.InProgress" in line:
            print("[SCAN] ⚠️ Scan already in progress. Resetting scan...")
            send_bt_command(proc, "scan off")
            time.sleep(3)
            send_bt_command(proc, "scan on")
            break

    found = False
    scan_start = time.time()

    try:
        while (time.time() - scan_start) < scan_timeout:
            line = _read_line_with_timeout(proc, 1)
            if not line:
                continue

            print(f"[SCAN] Output: {line.strip()}")

            if ("NEW" in line or "CHG" in line) and "Device" in line:
                parts = line.strip().split()
                if len(parts) >= 4:
                    mac = parts[2].upper().replace("-", ":")
                    name = " ".join(parts[3:])
                    if re.search(r'([0-9A-F]{2}-){2,}', name, re.IGNORECASE):
                        continue
                    if mac == target_mac:
                        print(f"[SCAN] ✅ Found target device {mac} with name '{name}'")
                        found = True
                        break
                    else:
                        print(f"[SCAN] Found different device {mac} → {name}")
        return found

    finally:
        print("[SCAN] 🔻 Stopping scan...")
        try:
            send_bt_command(proc, "scan off")
            time.sleep(1.5)
            # Confirm discovery stopped
            for _ in range(5):
                line = _read_line_with_timeout(proc, 1)
                if line and "Discovering: no" in line:
                    print("[SCAN] ✅ Discovery stopped.")
                    break
        except Exception as e:
            print(f"[SCAN] ⚠️ Error during scan shutdown: {e}")
