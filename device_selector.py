#!/usr/bin/env python3
import subprocess
import time
import tkinter as tk
from tkinter import messagebox, simpledialog
import re

def remove_ansi(text):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', text)

def scan_devices(scan_duration=10):
    """
    Start a temporary bluetoothctl subprocess, enable the agent,
    turn on scanning for a fixed duration, then stop scanning.
    Returns the complete scan output as a string.
    """
    proc = subprocess.Popen(
        ['bluetoothctl'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    # Turn on agent and set as default
    proc.stdin.write("agent on\n")
    proc.stdin.write("default-agent\n")
    proc.stdin.write("scan on\n")
    proc.stdin.flush()
    print("Scanning for devices for {} seconds...".format(scan_duration))
    time.sleep(scan_duration)
    proc.stdin.flush()
    time.sleep(2)  # Give a moment for scanning to stop
    try:
        output, _ = proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        output, _ = proc.communicate()
    return output

def parse_devices(scan_output):
    devices = {}
    for line in scan_output.splitlines():
        clean_line = remove_ansi(line).strip()
        print("DEBUG:", clean_line)  # Optional: print the cleaned line for debugging.
        if "NEW" in clean_line:
            parts = clean_line.split()
            # Ensure there are enough parts; here we expect at least 4 tokens.
            if len(parts) >= 4:
                mac = parts[2]  # e.g., "57:EE:5E:98:26:81"
                display_name = ""
                for part in range(3, len(parts)):
                     display_name += parts[part] + " "  # e.g., "57-EE-5E-98-26-81" or "classic300s"
                devices[mac] = display_name
    # Add paired devices
    try:
        paired_output = subprocess.check_output(
            ['bluetoothctl', 'devices', 'Paired'], universal_newlines=True
        )
        for line in paired_output.splitlines():
            clean_line = remove_ansi(line).strip()
            # Expected format: "Device <MAC> <DisplayName>"
            if clean_line.startswith("Device"):
                parts = clean_line.split()
                if len(parts) >= 3:
                    mac = parts[1]
                    display_name = " ".join(parts[2:]).strip()
                    # Only add if not already discovered
                    if mac not in devices:
                        devices[mac] = display_name
    except subprocess.CalledProcessError as e:
        print("Error retrieving paired devices:", e)


    return devices


def select_devices(devices):
    # Create the main window
    root = tk.Tk()
    root.title("Select Speakers")
    
    selected = {}  # Dictionary to store selected devices

    # Function to toggle device selection when a button is clicked
    def toggle_selection(mac, name, button):
        if mac in selected:
            # If already selected, unselect it and update button appearance
            del selected[mac]
            button.config(relief="raised")
        else:
            # Enforce a maximum of three devices
            if len(selected) >= 3:
                messagebox.showerror("Selection Limit", "You can select up to 3 devices.")
                return
            selected[mac] = name
            button.config(relief="sunken")

    # Create a frame to hold device buttons
    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10)

    # Dynamically create a button for each discovered device
    row = 0
    for mac, name in devices.items():
        btn = tk.Button(frame, text=name, width=30)
        # Capture the current button in the lambda by default argument b=btn
        btn.config(command=lambda m=mac, n=name, b=btn: toggle_selection(m, n, b))
        btn.grid(row=row, column=0, padx=5, pady=5)
        row += 1

    # Function to finalize selection when the Done button is pressed
    def finish():
        if not selected:
            if messagebox.askyesno("No Selection", "No devices were selected. Do you want to cancel?"):
                root.destroy()
                return
        root.destroy()

    # Create and pack the Done button
    finish_btn = tk.Button(root, text="Done", command=finish)
    finish_btn.pack(pady=10)
    
    # Start the Tkinter event loop
    root.mainloop()
    
    return selected








def set_volume(mac, volume):
    """
    Adjusts the volume of the speaker corresponding to the given MAC address.
    Assumes the BlueZ sink name is in the form:
    bluez_sink.<MAC_with_underscores>.a2dp_sink
    """
    # Replace colons with underscores in the MAC address.
    sink_name = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
    cmd = ["pactl", "set-sink-volume", sink_name, f"{volume}%"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error setting volume for {sink_name}: {e}")

def volume_control_page(speakers):
    """
    Creates a Tkinter window with a volume slider for each speaker.
    'speakers' should be a dictionary with keys as MAC addresses and
    values as display names.
    """
    root = tk.Tk()
    root.title("Speaker Volume Control")
    
    # Instruction label at the top.
    instr = tk.Label(root, text="Adjust the volume for each speaker:")
    instr.pack(padx=10, pady=10)
    
    # For each speaker, add a frame with a label and a slider.
    for mac, name in speakers.items():
        frame = tk.Frame(root)
        frame.pack(padx=10, pady=5, fill="x")
        
        # Display the speaker's name.
        label = tk.Label(frame, text=name, width=20, anchor="w")
        label.pack(side="left")
        
        # Create the slider (Scale widget).
        slider = tk.Scale(frame, from_=0, to=100, orient=tk.HORIZONTAL, length=200,
                          command=lambda val, mac=mac: set_volume(mac, int(val)))
        slider.set(50)  # Set the default volume to 50%.
        slider.pack(side="right", padx=10)
    
    # Optionally, add a Quit button.
    quit_btn = tk.Button(root, text="Close", command=root.destroy)
    quit_btn.pack(pady=10)
    
    root.mainloop()


# Global dictionary to store loopback module indices keyed by speaker MAC addresses.
loopback_modules = {}

def store_loopback_modules():
    """
    Queries PulseAudio for all loaded loopback modules using the virtual sink,
    extracts the module index and the associated speaker MAC (from the sink name),
    and stores them in the global 'loopback_modules' dictionary.
    """
    global loopback_modules
    loopback_modules.clear()  # Clear any existing entries.
    
    # Get the list of modules.
    output = subprocess.check_output(
        ["pactl", "list", "short", "modules"],
        universal_newlines=True
    )
    
    # Loop through each line and process modules that are loopbacks with our virtual sink.
    for line in output.splitlines():
        if "module-loopback" in line and "source=virtual_out.monitor" in line:
            # Expected format example:
            # 12    module-loopback    ... source=virtual_out.monitor sink=bluez_sink.98_52_3D_A3_C4_1B.a2dp_sink latency_msec=100
            parts = line.split()
            if not parts:
                continue
            module_index = parts[0]
            # Use regex to extract the MAC from the sink parameter.
            match = re.search(r'sink=bluez_sink\.([0-9A-Fa-f_]+)\.a2dp_sink', line)
            if match:
                mac_with_underscores = match.group(1)
                # Convert underscores to colons to get the proper MAC address.
                mac = mac_with_underscores.replace("_", ":")
                loopback_modules[mac] = module_index
    
    print("Loopback modules stored:", loopback_modules)



def load_loopback(mac, latency):
    """
    Loads a loopback module for a given speaker with the specified latency.
    Returns the module index as a string.
    """
    sink_name = f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"
    cmd = [
        "pactl", "load-module", "module-loopback",
        "source=virtual_out.monitor",
        f"sink={sink_name}",
        f"latency_msec={latency}"
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)
    module_index = result.stdout.strip()
    return module_index

def unload_loopback(module_index):
    """
    Unloads a loopback module given its module index.
    """
    subprocess.run(["pactl", "unload-module", module_index])

def set_latency(mac, latency):
    """
    Adjusts the latency for the loopback module associated with a given speaker.
    It unloads the current module (if exists) and reloads it with the new latency.
    """
    print(f"Setting latency for {mac} to {latency} ms.")
    if mac in loopback_modules:
        unload_loopback(loopback_modules[mac])
    module_index = load_loopback(mac, latency)
    loopback_modules[mac] = module_index
    print(f"Loopback for {mac} updated: new module index {module_index}")

def latency_control_page(speakers):
    """
    Creates a Tkinter window with a latency slider for each speaker.
    'speakers' should be a dictionary with keys as MAC addresses and values as display names.
    """
    root = tk.Tk()
    root.title("Speaker Latency Control")

    instr = tk.Label(root, text="Adjust the latency (ms) for each speaker:")
    instr.pack(padx=10, pady=10)

    # Create a slider for each speaker.
    for mac, name in speakers.items():
        frame = tk.Frame(root)
        frame.pack(padx=10, pady=5, fill="x")
        
        label = tk.Label(frame, text=name, width=20, anchor="w")
        label.pack(side="left")
        
        # Create the slider (from 0 to 500 ms, for example)
        slider = tk.Scale(frame, from_=0, to=500, orient=tk.HORIZONTAL, length=200,
                          command=lambda val, mac=mac: set_latency(mac, int(val)))
        slider.set(100)  # Set default latency to 100 ms.
        slider.pack(side="right", padx=10)

    quit_btn = tk.Button(root, text="Close", command=root.destroy)
    quit_btn.pack(pady=10)
    
    root.mainloop()





def main():
    # Step 1: Run the scan.
    scan_output = scan_devices(scan_duration=10)

    with open("scan_output.txt", "w") as f:
        f.write(scan_output)
    for line in scan_output.splitlines():
        print("this is a line:")
        print(line.strip().split())
    # Step 2: Parse the scan output using our filter.
    devices = parse_devices(scan_output)
    print("Parsed devices:")
    for mac, name in devices.items():
        print(f"{name} ({mac})")
    
    # Step 3: Display the GUI for selection.
    selected_devices = select_devices(devices)
    print("Selected devices:")
    for mac, name in selected_devices.items():
        print(f"{name} ({mac})")
    
    # Step 4: Save the selected devices for later use (or pass them to your pairing code).
    with open("selected_devices.txt", "w") as f:
        for mac, name in selected_devices.items():
            f.write(f"{mac},{name}\n")
    print("Selected devices saved to selected_devices.txt")


    subprocess.run(["./pair_selected_devices.sh"], check=True)

    store_loopback_modules()

    volume_control_page(selected_devices)


    latency_control_page(selected_devices)


if __name__ == '__main__':
    main()

