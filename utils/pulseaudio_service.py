# utils/pulseaudio.py
import subprocess
import time
from typing import List, Optional

HEADER = '\033[95m'
BLUE = '\033[94m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
ENDC = '\033[0m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'

# utils/pulseaudio.py (add this function)
import subprocess
from utils.logging import log
from utils.global_state import GLOBAL_BLUETOOTH_STATE  

def cleanup_pulseaudio():
    try:
        log(f"{YELLOW}Cleaning up PulseAudio sinks and loopbacks...{ENDC}")
        
        # Get all modules in short format
        log(f"{BLUE}Fetching module list...{ENDC}")
        modules_output = subprocess.run(["pactl", "list", "modules", "short"], capture_output=True, text=True)
        if modules_output.returncode != 0:
            log(f"{RED}Error getting module list: {modules_output.stderr}{ENDC}")
            return False
            
        # Process each line and unload matching modules
        for line in modules_output.stdout.splitlines():
            if not line.strip():
                continue
                
            # Split the line into parts (module_id, name, args)
            parts = line.split('\t')
            if len(parts) < 2:
                continue
                
            module_id = parts[0]
            module_name = parts[1]
            
            # Unload if it's a loopback module or contains virtual_out/bluez_sink
            if "module-loopback" in module_name or "virtual_out" in line or "bluez_sink" in line:
                log(f"{YELLOW}Found module to remove: {line}{ENDC}")
                unload_result = subprocess.run(["pactl", "unload-module", module_id], capture_output=True, text=True)
                if unload_result.returncode != 0:
                    log(f"{RED}Error unloading module {module_id}: {unload_result.stderr}{ENDC}")
                else:
                    log(f"{GREEN}Successfully unloaded module {module_id}{ENDC}")
        
        # Verify cleanup
        log(f"{BLUE}Verifying cleanup...{ENDC}")
        verify_modules = subprocess.run(["pactl", "list", "modules", "short"], capture_output=True, text=True)
        remaining_modules = [line for line in verify_modules.stdout.splitlines() 
                           if "module-loopback" in line or "virtual_out" in line or "bluez_sink" in line]
        
        if remaining_modules:
            log(f"{RED}Warning: Remaining modules found: {remaining_modules}{ENDC}")
        
        log(f"{GREEN}PulseAudio cleanup completed{ENDC}")
        return True
    except Exception as e:
        log(f"{RED}Error during PulseAudio cleanup: {str(e)}{ENDC}")
        log(f"{RED}Error type: {type(e).__name__}{ENDC}")
        import traceback
        log(f"{RED}Traceback: {traceback.format_exc()}{ENDC}")
        return False
    

def remove_loopback_for_device(mac: str):
    sink_name = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
    subprocess.call(["pactl", "unload-module", f"module-loopback sink={sink_name}"])


def partial_cleanup_pulseaudio(allowed_macs):
    """
    Unloads loopback modules for any MAC not in allowed_macs.
    Leaves all loopbacks for allowed_macs intact.
    """
    import subprocess

    # 1. List all modules
    modules_output = subprocess.run(
        ["pactl", "list", "modules", "short"],
        capture_output=True,
        text=True
    )
    if modules_output.returncode != 0:
        log(f"Error listing modules: {modules_output.stderr}")
        return

    for line in modules_output.stdout.splitlines():
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        
        module_id = cols[0]
        module_args = cols[1]

        # Check if it's a loopback referencing a specific MAC
        # Example line:  "22    module-loopback sink=bluez_output.AA_BB_CC_DD_EE_FF.1 ..."
        # We search for any mac that matches.
        if "module-loopback" in module_args:
            # Attempt to parse out the MAC from the sink name
            # E.g. "bluez_output.AA_BB_CC_DD_EE_FF.1"
            # or "bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink" etc.
            
            # A naive approach:
            for mac in allowed_macs:
                mac_underscore = mac.replace(":", "_")
                registered_sink = GLOBAL_BLUETOOTH_STATE["loopbacks"].get(mac)
                if mac_underscore in module_args or (registered_sink and registered_sink in module_args):
                    # This loopback is for an allowed device
                    break
            else:
                # If we never broke out, it's not an allowed device → unload
                log(f"Unloading loopback module {module_id}, because it's not in allowed list.")
                subprocess.run(["pactl", "unload-module", module_id])

def is_pipewire():
    try:
        info = subprocess.run(["pactl", "info"], capture_output=True, text=True)
        return "PulseAudio (on PipeWire" in info.stdout
    except Exception:
        return False
    

def setup_pulseaudio():
    import subprocess
    import time

    try:
        # Step 1: Check if PulseAudio is responsive
        info_result = subprocess.run(["pactl", "info"], capture_output=True, text=True)
        if info_result.returncode != 0 or "Server Name" not in info_result.stdout:
            log("⚠️ PulseAudio is not responsive. Attempting restart...")

            # Kill existing PulseAudio processes
            subprocess.run(["pkill", "-9", "pulseaudio"], check=False)
            time.sleep(1)

            # Start a new session
            subprocess.run(["pulseaudio", "--start"], check=False)
            log("🔁 PulseAudio restarted. Waiting for it to come online...")

            # Wait for it to respond
            for i in range(5):
                result = subprocess.run(["pactl", "info"], capture_output=True, text=True)
                if result.returncode == 0 and "Server Name" in result.stdout:
                    log("✅ PulseAudio is now responsive.")
                    break
                time.sleep(1)
            else:
                log("❌ PulseAudio failed to become responsive after restart.")
                return False
        else:
            log("✅ PulseAudio is already running and responsive.")

        # Step 2: Check if virtual_out sink already exists
        existing = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True)
        if "virtual_out" in existing.stdout:
            log("✅ virtual_out already exists. Skipping creation.")
            return True

        # Step 3: Load virtual sink
        result = subprocess.run([
            "pactl", "load-module", "module-null-sink",
            "sink_name=virtual_out",
            "sink_properties=device.description=virtual_out"
        ], capture_output=True, text=True)

        if result.returncode != 0:
            log(f"❌ Failed to create virtual sink: {result.stderr.strip()}")
            return False

        log(f"✅ Virtual sink created with index: {result.stdout.strip()}")

        # Step 4: Set it as the default sink
        set_result = subprocess.run(["pactl", "set-default-sink", "virtual_out"], capture_output=True, text=True)
        if set_result.returncode != 0:
            log(f"⚠️ Warning: Could not set default sink: {set_result.stderr.strip()}")
            return False

        log("✅ Set virtual_out as the default sink.")
        return True

    except Exception as e:
        log(f"❌ Error setting up PulseAudio: {e}")
        return False




def create_loopback(expected_sink_prefix: str, latency_ms: int = 100, wait_seconds: int = 20) -> bool:
    """
    Waits for a specific sink to appear (matching by prefix), unloads any existing loopbacks for it,
    and then creates a clean new loopback.
    """
    def find_actual_sink_name() -> str:
        result = subprocess.run(["pactl", "list", "sinks", "short"],
                                capture_output=True, text=True)
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith(expected_sink_prefix):
                return parts[1]
        return None

    def unload_conflicting_loopbacks(actual_sink_name: str):
        modules_output = subprocess.run(["pactl", "list", "short", "modules"],
                                        capture_output=True, text=True)
        for line in modules_output.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and "module-loopback" in parts[1] and actual_sink_name in line:
                module_id = parts[0]
                log(f"🧹 Unloading conflicting loopback module {module_id} for sink {actual_sink_name}")
                subprocess.run(["pactl", "unload-module", module_id])

    def load_loopback(actual_sink_name: str):
        result = subprocess.run([
            "pactl", "load-module", "module-loopback",
            "source=virtual_out.monitor",
            f"sink={actual_sink_name}",
            f"latency_msec={latency_ms}"
        ], capture_output=True, text=True)
        return result

    log(f"⏳ Waiting for sink '{expected_sink_prefix}' to appear...")
    for _ in range(wait_seconds * 2):
        actual_sink_name = find_actual_sink_name()
        if actual_sink_name:
            log(f"✅ Sink '{actual_sink_name}' found (matches '{expected_sink_prefix}').")
            unload_conflicting_loopbacks(actual_sink_name)
            result = load_loopback(actual_sink_name)
            if result.returncode == 0:
                log(f"✅ Loopback for {actual_sink_name} created successfully (module index: {result.stdout.strip()})")
                return True
            else:
                log(f"❌ Failed to create loopback for {actual_sink_name}: {result.stderr.strip()}")
                return False
        time.sleep(0.5)

    log(f"❌ Sink '{expected_sink_prefix}' did not appear within {wait_seconds} seconds.")
    return False



