import select
import subprocess
import re
import time


def _read_line_with_timeout(proc, timeout_s):
    """
    Reads a line from proc.stdout with a real timeout using select.
    """
    fd = proc.stdout.fileno()
    ready, _, _ = select.select([fd], [], [], timeout_s)
    if ready:
        return proc.stdout.readline()
    return None


def send_bt_command(proc, command, wait=0.5):
    proc.stdin.write(f"{command}\n")
    proc.stdin.flush()
    time.sleep(wait)

def pair_device(proc, mac, timeout=10):
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

        if "Pairing successful" in line or "Paired: yes" in line:
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



def connect_device(proc, mac, timeout=10):
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