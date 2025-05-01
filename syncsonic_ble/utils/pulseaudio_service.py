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



def remove_loopback_for_device(mac: str):
    sink_name = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
    subprocess.call(["pactl", "unload-module", f"module-loopback sink={sink_name}"])

    

def setup_pulseaudio():
    import subprocess
    import time

    try:
        # Step 1: Check if PulseAudio is responsive
        info_result = subprocess.run(["pactl", "info"], capture_output=True, text=True)
        if info_result.returncode != 0 or "Server Name" not in info_result.stdout:
           

            # Kill existing PulseAudio processes
            subprocess.run(["pkill", "-9", "pulseaudio"], check=False)
            time.sleep(1)

            # Start a new session
            subprocess.run(["pulseaudio", "--start"], check=False)
           

            # Wait for it to respond
            for i in range(5):
                result = subprocess.run(["pactl", "info"], capture_output=True, text=True)
                if result.returncode == 0 and "Server Name" in result.stdout:
                  
                    break
                time.sleep(1)
            else:
       
                return False

      

        # Step 2: Check if virtual_out sink already exists
        existing = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True)
        if "virtual_out" in existing.stdout:
        
            return True

        # Step 3: Load virtual sink
        result = subprocess.run([
            "pactl", "load-module", "module-null-sink",
            "sink_name=virtual_out",
            "sink_properties=device.description=virtual_out"
        ], capture_output=True, text=True)

        if result.returncode != 0:
          
            return False


        # Step 4: Set it as the default sink
        set_result = subprocess.run(["pactl", "set-default-sink", "virtual_out"], capture_output=True, text=True)
        if set_result.returncode != 0:
        
            return False

        return True

    except Exception as e:
   
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

                subprocess.run(["pactl", "unload-module", module_id])

    def load_loopback(actual_sink_name: str):
        result = subprocess.run([
            "pactl", "load-module", "module-loopback",
            "source=virtual_out.monitor",
            f"sink={actual_sink_name}",
            f"latency_msec={latency_ms}"
        ], capture_output=True, text=True)
        return result

    for _ in range(wait_seconds * 2):
        actual_sink_name = find_actual_sink_name()
        if actual_sink_name:
   
            unload_conflicting_loopbacks(actual_sink_name)
            result = load_loopback(actual_sink_name)
            if result.returncode == 0:
      
                return True
            else:
      
                return False
        time.sleep(0.5)


    return False



