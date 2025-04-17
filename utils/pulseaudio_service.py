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

    try:
        # First check if a virtual_out sink already exists
        existing = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True)
        if "virtual_out" in existing.stdout:
            log("✅ virtual_out already exists. Skipping creation.")
            return True

        result = subprocess.run([
            "pactl", "load-module", "module-null-sink",
            "sink_name=virtual_out",
            "sink_properties=device.description=virtual_out"
        ], capture_output=True, text=True)

        log(f"✅ Virtual sink created with index: {result.stdout.strip()}")
        # 💡 Set it as the default sink
        subprocess.run(["pactl", "set-default-sink", "virtual_out"], check=True)
        log("✅ Set virtual_out as the default sink")

        return True

    except Exception as e:
        log(f"❌ Error setting up PulseAudio: {e}")
        return False

def create_loopback(sink_name: str, latency_ms: int = 100) -> bool:
    """
    Attempt to create a loopback from virtual_out.monitor to the given sink with specified latency.
    Retries once if the first attempt fails.
    """
    def try_create():
        return subprocess.run([
            "pactl", "load-module", "module-loopback",
            "source=virtual_out.monitor",
            f"sink={sink_name}",
            f"latency_msec={latency_ms}"
        ], capture_output=True, text=True)

    result = try_create()

    if result.returncode == 0:
        log(f"✅ Loopback for {sink_name} loaded with index: {result.stdout.strip()}")
        return True
    else:
        log(f"⚠️ First attempt to load loopback for {sink_name} failed: {result.stderr.strip()}")
        time.sleep(1)  # give the sink a moment to become active
        log(f"🔁 Retrying loopback creation for {sink_name}...")
        result = try_create()
        if result.returncode == 0:
            log(f"✅ Loopback for {sink_name} loaded on retry with index: {result.stdout.strip()}")
            return True
        else:
            log(f"❌ Retry also failed to load loopback for {sink_name}: {result.stderr.strip()}")
            return False



