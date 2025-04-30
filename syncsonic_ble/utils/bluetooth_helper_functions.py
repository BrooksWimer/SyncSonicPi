import select
import subprocess
import re
import time
from utils.pulseaudio_service import remove_loopback_for_device
from pydbus import SystemBus
from utils.logging import log


def _read_line_with_timeout(proc, timeout_s):
    """
    Reads a line from proc.stdout with a real timeout using select.
    """
    fd = proc.stdout.fileno()
    ready, _, _ = select.select([fd], [], [], timeout_s)
    if ready:
        return proc.stdout.readline()
    return None

# def wait_for_prompt(proc, timeout=3.0):
#     """
#     Waits for a bluetoothctl-style prompt (like [bluetooth]# or [DeviceName]#).
#     Returns True if a valid prompt is detected, False if timeout or connection issue.
#     """
#     import time
#     import re

#     start = time.time()
#     prompt_pattern = re.compile(r"\[[^\]]+\]#")
#     while time.time() - start < timeout:
#         line = _read_line_with_timeout(proc, 0.5)
#         if line:
#             line = line.strip()
#             print(f"[PROMPT] Output: {line}")
#             if "Waiting to connect to bluetoothd" in line:
#                 print("[PROMPT] ❌ Bluetoothd not available. Aborting.")
#                 return False
#             if prompt_pattern.search(line):
#                 return True
#     return False


# def send_bt_command(proc, command, wait=0.5, retries=2, confirm_echo=True):
#     """
#     Sends a command to bluetoothctl. Assumes we're already in a usable prompt.
#     Tries to confirm via echo or prompt response after sending.
#     """
#     import time
#     import re

#     for attempt in range(retries + 1):
#         print(f"[SEND] Attempt {attempt + 1}: sending '{command}'")

#         try:
#             proc.stdin.write(f"{command}\n")
#             proc.stdin.flush()
#             time.sleep(wait)

#             if confirm_echo:
#                 for _ in range(5):
#                     line = _read_line_with_timeout(proc, 1)
#                     if line:
#                         line = line.strip()
#                         print(f"[SEND] Echo: {line}")
#                         if command.split()[0] in line or re.search(r"\[[^\]]+\]#", line):
#                             return True
#                 print(f"[SEND] ⚠️ No echo or prompt confirmation for '{command}'")

#             return True  # Acceptable even if no echo, to keep things moving

#         except Exception as e:
#             print(f"[SEND] ❌ Error sending '{command}': {e}")

#         time.sleep(1.0)

#     print(f"[SEND] ❌ Failed to send '{command}' after {retries + 1} attempts.")
#     return False

def send_bt_command(proc, command, wait=0.5):
    proc.stdin.write(f"{command}\n")
    proc.stdin.flush()
    time.sleep(wait)



def pair_device(proc, mac, timeout=20):
    print(f"[PAIR] Pairing with {mac}...")
    send_bt_command(proc, f"pair {mac}")
    start_time = time.time()

    while True:
        # Check if we’ve exceeded the timeout window
        if time.time() - start_time > timeout:
            print("[PAIR] ❌ Timed out.")
            return False

        line = _read_line_with_timeout(proc, timeout)
        if not line:
            continue
        line = line.strip()
        print(f"[PAIR] Output: {line}")

        if "Pairing successful" in line or "Paired: yes" in line or "LegacyPairing: yes" in line or "Connected: yes" in line:
            print("[PAIR] ✅ Pairing successful.")
            return True
        if "AlreadyExists" in line or "Already paired" in line:
            print("[PAIR] ⚠️ Already paired. Continuing...")
            return True
        if "Failed to pair" in line or "AuthenticationRejected" in line or "org.bluez.Error" in line:
            print("[PAIR] ❌ Pairing failed.")
            return False


def trust_device(proc, mac, timeout=10):
    print(f"[TRUST] Trusting {mac}...")
    send_bt_command(proc, f"trust {mac}")
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout:
            print("[TRUST] ❌ Timed out.")
            return False

        line = _read_line_with_timeout(proc, timeout)
        if not line:
            continue
        line = line.strip()
        print(f"[TRUST] Output: {line}")

        if "trust succeeded" in line.lower() or "Trusted: yes" in line:
            print("[TRUST] ✅ Trust successful.")
            return True
        if "AlreadyTrusted" in line or "already trusted" in line.lower():
            print("[TRUST] ⚠️ Already trusted. Continuing...")
            return True
        if "Failed to trust" in line or "org.bluez.Error" in line:
            print("[TRUST] ❌ Trust failed.")
            return False



def connect_device(proc, mac, timeout=20):
    print(f"[CONNECT] Connecting to {mac}...")
    send_bt_command(proc, f"connect {mac}")
    start_time = time.time()
    retry_once = False

    while True:
        if time.time() - start_time > timeout:
            print("[CONNECT] ❌ Timed out.")
            return False

        line = _read_line_with_timeout(proc, timeout)
        if not line:
            continue
        line = line.strip()
        print(f"[CONNECT] Output: {line}")

        if "Connection successful" in line or "Connected: yes" in line:
            print("[CONNECT] ✅ Connected successfully.")
            return True

        if "AlreadyConnected" in line:
            print("[CONNECT] ⚠️ Already connected. Continuing...")
            return True

        if "br-connection-already-connected" in line and not retry_once:
            print("[CONNECT] ⚠️ Already connected at BR level. Disconnecting and retrying...")
            send_bt_command(proc, f"disconnect {mac}")
            time.sleep(1)
            send_bt_command(proc, f"connect {mac}")
            retry_once = True
            continue

        if "Failed to connect" in line or "org.bluez.Error" in line:
            print("[CONNECT] ❌ Connect failed.")
            return False



def bt_select_controller(proc, mac, retries=3, delay=0.5):
    for attempt in range(retries):
        try:
            send_bt_command(proc, f"select {mac}")
            for _ in range(5):  # Read up to 5 lines
                line = _read_line_with_timeout(proc, 1)
                if line:
                    print(f"[SELECT] Output: {line.strip()}")
                    if f"Controller" in line:
                        return True
                    else:
                        return True
        except Exception as e:
            print(f"[SELECT] Attempt {attempt+1} failed: {e}")
        time.sleep(delay)
    return True



def bt_power_on(proc, retries=3, delay=0.5):
    for attempt in range(retries):
        try:
            send_bt_command(proc, "power on")
            for _ in range(3):
                line = _read_line_with_timeout(proc, 1)
                if line and "succeeded" in line:
                    return True
        except Exception as e:
            print(f"[POWER] Attempt {attempt+1} failed: {e}")
        time.sleep(delay)
    return False


def bt_set_agent(proc, retries=3, delay=0.5):
    for attempt in range(retries):
        try:
            send_bt_command(proc, "agent off")
            time.sleep(0.3)

            send_bt_command(proc, "agent NoInputNoOutput")
            time.sleep(0.3)

            send_bt_command(proc, "default-agent")

            for _ in range(5):
                line = _read_line_with_timeout(proc, 1)
                if line and ("Agent registered" in line or "Default agent request successful" in line):
                    return True
        except Exception as e:
            print(f"[AGENT] Attempt {attempt+1} failed: {e}")
        time.sleep(delay)
    return False


def bt_scan_off(proc, retries=3, delay=0.5):
    for attempt in range(retries):
        try:
            send_bt_command(proc, "scan off")
            time.sleep(delay)
            return True  # even if no confirmation, it's generally safe
        except Exception as e:
            print(f"[SCAN OFF] Attempt {attempt+1} failed: {e}")
        time.sleep(delay)
    return False


def bt_scan_on(proc, retries=3, delay=0.5):
    for attempt in range(retries):
        try:
            send_bt_command(proc, "scan on")
            for _ in range(5):
                line = _read_line_with_timeout(proc, 1)
                if line and "Discovery started" in line:
                    return True
        except Exception as e:
            print(f"[SCAN ON] Attempt {attempt+1} failed: {e}")
        time.sleep(delay)
    return False

def stop_discovery_all_hcis():
    try:
        # List all adapters using 'busctl tree'
        result = subprocess.run(
            ["busctl", "tree", "org.bluez"],
            capture_output=True, text=True
        )
        hci_paths = re.findall(r"/org/bluez/hci[0-9]+", result.stdout)
        unique_hcis = sorted(set(hci_paths))

        for hci_path in unique_hcis:
            print(f"🛑 Stopping discovery on {hci_path}...")
            stop_result = subprocess.run([
                "busctl", "call", "org.bluez", hci_path,
                "org.bluez.Adapter1", "StopDiscovery"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if stop_result.returncode == 0:
                print(f"✅ Stopped discovery on {hci_path}")
            else:
                print(f"⚠️ Failed to stop discovery on {hci_path}: {stop_result.stderr.strip()}")

    except Exception as e:
        print(f"❌ Error while stopping discovery: {e}")


def remove_device(proc, mac, timeout=10):
    print(f"[REMOVE] Removing {mac}...")
    send_bt_command(proc, f"remove {mac}")
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout:
            print("[REMOVE] ❌ Timed out.")
            return False

        line = _read_line_with_timeout(proc, timeout)
        if not line:
            continue
        line = line.strip()
        print(f"[REMOVE] Output: {line}")

        if "Device has been removed" in line or "Device removed" in line:
            print("[REMOVE] ✅ Device removed successfully.")
            return True
        if "not available" in line or "does not exist" in line:
            print("[REMOVE] ⚠️ Device not found, assuming removed.")
            return True
        if "Failed to remove" in line or "org.bluez.Error" in line:
            print("[REMOVE] ❌ Removal failed.")
            return False
