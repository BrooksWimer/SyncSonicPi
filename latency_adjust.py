#!/usr/bin/env python3
import tkinter as tk
import subprocess

# Global variables to store module IDs for each loopback
master_module_id = None
slave_module_id = None

def update_master(event=None):
    global master_module_id
    master_delay = master_slider.get()  # in milliseconds
    status_label_master.config(text=f"Master delay: {master_delay} ms")
    print(f"Setting master delay to: {master_delay} ms")
    
    # Unload the current master loopback module if it's loaded
    if master_module_id is not None:
        subprocess.run(["pactl", "unload-module", str(master_module_id)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Load the loopback for the master speaker with the new delay value
    result = subprocess.run([
        "pactl", "load-module", "module-loopback",
        "source=virtual_sink.monitor",
        "sink=bluez_output.00_0C_8A_FF_18_FE.1",
        f"latency_msec={master_delay}"
    ], capture_output=True, text=True)
    try:
        master_module_id = int(result.stdout.strip())
    except ValueError:
        master_module_id = None

def update_slave(event=None):
    global slave_module_id
    slave_delay = slave_slider.get()  # in milliseconds
    status_label_slave.config(text=f"Slave delay: {slave_delay} ms")
    print(f"Setting slave delay to: {slave_delay} ms")
    
    # Unload the current slave loopback module if it's loaded
    if slave_module_id is not None:
        subprocess.run(["pactl", "unload-module", str(slave_module_id)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Load the loopback for the slave speaker with the new delay value
    result = subprocess.run([
        "pactl", "load-module", "module-loopback",
        "source=virtual_sink.monitor",
        "sink=bluez_output.98_52_3D_A3_C4_1B.1",
        f"latency_msec={slave_delay}"
    ], capture_output=True, text=True)
    try:
        slave_module_id = int(result.stdout.strip())
    except ValueError:
        slave_module_id = None

# Create the main window
root = tk.Tk()
root.title("Independent Speaker Latency Adjustment")

# Master slider and label
tk.Label(root, text="Master Speaker Delay (ms)").pack()
master_slider = tk.Scale(root, from_=0, to=5000, orient="horizontal")
master_slider.pack(pady=10)
status_label_master = tk.Label(root, text="Master delay: 0 ms")
status_label_master.pack()
master_slider.bind("<ButtonRelease-1>", update_master)

# Slave slider and label
tk.Label(root, text="Slave Speaker Delay (ms)").pack()
slave_slider = tk.Scale(root, from_=0, to=5000, orient="horizontal")
slave_slider.pack(pady=10)
status_label_slave = tk.Label(root, text="Slave delay: 0 ms")
status_label_slave.pack()
slave_slider.bind("<ButtonRelease-1>", update_slave)

tk.Label(root, text="Release the slider to update delay immediately.").pack(pady=10)

root.mainloop()
