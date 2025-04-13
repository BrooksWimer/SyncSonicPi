# utils/pulseaudio.py
import subprocess
import time
from .logging import log, RED, GREEN, YELLOW
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
from .logging import log

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


def is_pipewire():
    try:
        info = subprocess.run(["pactl", "info"], capture_output=True, text=True)
        return "PulseAudio (on PipeWire" in info.stdout
    except Exception:
        return False

def setup_pulseaudio():
    try:
        # Only try to start pulseaudio if not using pipewire
        if not is_pipewire():
            subprocess.run(["pulseaudio", "--start"], check=True)
            time.sleep(2)

        result = subprocess.run([
            "pactl", "load-module", "module-null-sink",
            "sink_name=virtual_out",
            "sink_properties=device.description=virtual_out"
        ], capture_output=True, text=True)

        log(f"Virtual sink created with index: {result.stdout.strip()}")
        return True
    except Exception as e:
        log(f"Error setting up PulseAudio: {e}")
        return False

def create_loopback(sink_name):
    try:
        result = subprocess.run([
            "pactl", "load-module", "module-loopback",
            "source=virtual_out.monitor",
            f"sink={sink_name}",
            "latency_msec=100"
        ], capture_output=True, text=True)
        log(f"Loopback for {sink_name} loaded with index: {result.stdout.strip()}")
        return True
    except Exception as e:
        log(f"Error creating loopback for {sink_name}: {e}")
        return False

