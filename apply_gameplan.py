#!/usr/bin/env python3
import sys
import time
import json
from pydbus import SystemBus

def log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}")

###########################################################################
# Helper: Get managed objects from BlueZ.
###########################################################################
def get_managed_objects(bus):
    manager = bus.get("org.bluez", "/")
    return manager.GetManagedObjects()

###########################################################################
# Helper: Find an adapter by its Address property.
###########################################################################
def get_adapter_by_address(bus, adapter_address, objects):
    for path, ifaces in objects.items():
        adapter = ifaces.get("org.bluez.Adapter1")
        if adapter and "Address" in adapter and adapter["Address"].upper() == adapter_address.upper():
            return path, bus.get("org.bluez", path)
    return None, None

###########################################################################
# Helper: Find a device (object path and object) under an adapter.
###########################################################################
def get_device_by_address(bus, adapter_path, device_address, objects):
    for path, ifaces in objects.items():
        if not path.startswith(adapter_path):
            continue
        device = ifaces.get("org.bluez.Device1")
        if device and "Address" in device and device["Address"].upper() == device_address.upper():
            return path, bus.get("org.bluez", path)
    return None, None

###########################################################################
# Device operations via BlueZ D-Bus API.
###########################################################################
def disconnect_device(bus, adapter_addr, device_addr):
    objects = get_managed_objects(bus)
    adapter_path, adapter_obj = get_adapter_by_address(bus, adapter_addr, objects)
    if not adapter_obj:
        log(f"Adapter {adapter_addr} not found.")
        return False
    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
    if not device_obj:
        log(f"Device {device_addr} not found under adapter {adapter_addr}.")
        return False
    try:
        log(f"Disconnecting device {device_addr} from adapter {adapter_addr}...")
        device_obj.Disconnect()
        time.sleep(2)
        return True
    except Exception as e:
        log(f"Error disconnecting {device_addr} on {adapter_addr}: {e}")
        return False

def pair_and_connect(bus, adapter_addr, device_addr):
    objects = get_managed_objects(bus)
    adapter_path, adapter_obj = get_adapter_by_address(bus, adapter_addr, objects)
    if not adapter_obj:
        log(f"Adapter {adapter_addr} not found.")
        return False
    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
    if not device_obj:
        log(f"Device {device_addr} not found under adapter {adapter_addr}.")
        return False
    try:
        log(f"Starting discovery on adapter {adapter_addr}...")
        adapter_obj.StartDiscovery()
        time.sleep(5)
        adapter_obj.StopDiscovery()
        max_wait = 5
        start = time.time()
        while adapter_obj.Discovering and (time.time() - start < max_wait):
            log(f"Waiting for adapter {adapter_addr} to stop discovering...")
            time.sleep(1)
    except Exception as e:
        log(f"Discovery error on adapter {adapter_addr}: {e}")
    try:
        if not device_obj.Paired:
            log(f"Pairing device {device_addr} on adapter {adapter_addr}...")
            device_obj.Pair()
            time.sleep(5)
        else:
            log(f"Device {device_addr} already paired.")
    except Exception as e:
        log(f"Pairing error for device {device_addr} on adapter {adapter_addr}: {e}")
        return False
    try:
        device_obj.Trusted = True
        log(f"Device {device_addr} set as Trusted.")
    except Exception as e:
        log(f"Error setting Trusted for device {device_addr}: {e}")
    try:
        log(f"Connecting device {device_addr} on adapter {adapter_addr}...")
        device_obj.Connect()
        time.sleep(3)
    except Exception as e:
        log(f"Connection error for device {device_addr} on adapter {adapter_addr}: {e}")
        return False
    objects = get_managed_objects(bus)
    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
    if device_obj and device_obj.Connected:
        log(f"Device {device_addr} successfully connected on adapter {adapter_addr}.")
        return True
    else:
        log(f"Device {device_addr} did not appear as connected on adapter {adapter_addr}.")
        return False

def connect_only(bus, adapter_addr, device_addr):
    objects = get_managed_objects(bus)
    adapter_path, adapter_obj = get_adapter_by_address(bus, adapter_addr, objects)
    if not adapter_obj:
        log(f"Adapter {adapter_addr} not found.")
        return False
    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
    if not device_obj:
        log(f"Device {device_addr} not found under adapter {adapter_addr}.")
        return False
    try:
        log(f"Starting discovery on adapter {adapter_addr}...")
        adapter_obj.StartDiscovery()
        time.sleep(5)
        adapter_obj.StopDiscovery()
        max_wait = 5
        start = time.time()
        while adapter_obj.Discovering and (time.time() - start < max_wait):
            log(f"Waiting for adapter {adapter_addr} to stop discovering...")
            time.sleep(1)
    except Exception as e:
        log(f"Discovery error on adapter {adapter_addr}: {e}")
    try:
        log(f"Connecting device {device_addr} on adapter {adapter_addr}...")
        device_obj.Connect()
        time.sleep(3)
    except Exception as e:
        log(f"Connection error for device {device_addr} on adapter {adapter_addr}: {e}")
        return False
    objects = get_managed_objects(bus)
    dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
    if device_obj and device_obj.Connected:
        log(f"Device {device_addr} successfully connected on adapter {adapter_addr}.")
        return True
    else:
        log(f"Device {device_addr} did not appear as connected on adapter {adapter_addr}. Retrying...")
        time.sleep(3)
        try:
            device_obj.Connect()
            time.sleep(3)
        except Exception as e:
            log(f"Retry connection error for device {device_addr} on adapter {adapter_addr}: {e}")
            return False
        objects = get_managed_objects(bus)
        dev_path, device_obj = get_device_by_address(bus, adapter_path, device_addr, objects)
        if device_obj and device_obj.Connected:
            log(f"Device {device_addr} successfully connected on adapter {adapter_addr} after retry.")
            return True
        else:
            log(f"Device {device_addr} still did not appear as connected on adapter {adapter_addr}.")
            return False

###########################################################################
# Main: Process gameplan JSON input, apply connection flow, and record status.
#
# Usage: python3 apply_gameplan.py <gameplan.json>
###########################################################################
def main():
    if len(sys.argv) != 2:
        log("Usage: python3 apply_gameplan.py <gameplan.json>")
        sys.exit(1)

    with open(sys.argv[1], "r") as f:
        gameplan = json.load(f)

    bus = SystemBus()
    connection_status = {}  # Will store status per speaker.

    for sp_mac, details in gameplan.items():
        sp_name = details.get("name")
        action = details.get("action", "")
        disconnect_list = details.get("disconnect", [])
        log(f"Processing {sp_name} ({sp_mac}) with action: {action}")

        # Disconnect from any adapters in disconnect list.
        for adapter in disconnect_list:
            log(f"Disconnecting {sp_mac} from adapter {adapter}...")
            disconnect_device(bus, adapter, sp_mac)

        # Extract recommended adapter from the action text.
        rec_adapter = None
        parts = action.split("controller")
        if len(parts) > 1:
            rec_adapter = parts[1].strip().split()[0]
            log(f"Recommended adapter for {sp_mac} is {rec_adapter}.")
        else:
            log(f"No recommended adapter found for {sp_mac}.")

        result = None
        if action.startswith("No action"):
            log(f"{sp_name} ({sp_mac}) already connected. Skipping connection.")
            result = "Connected"
        elif "Pair and connect" in action:
            if rec_adapter:
                log(f"Pairing and connecting {sp_name} ({sp_mac}) using adapter {rec_adapter}...")
                result = pair_and_connect(bus, rec_adapter, sp_mac)
                result = "Connected" if result else "Error in Pair and Connect"
            else:
                log(f"Error: No adapter specified for pairing {sp_mac}.")
                result = "Error: No adapter"
        elif "Connect using" in action:
            if rec_adapter:
                log(f"Connecting {sp_name} ({sp_mac}) using adapter {rec_adapter}...")
                result = connect_only(bus, rec_adapter, sp_mac)
                result = "Connected" if result else "Error in Connect Only"
            else:
                log(f"Error: No adapter specified for connecting {sp_mac}.")
                result = "Error: No adapter"
        else:
            log(f"Unrecognized action for {sp_name} ({sp_mac}): {action}. Skipping.")
            result = "Error: Unrecognized action"

        connection_status[sp_mac] = {"name": sp_name, "result": result}

    log("Gameplan processing complete.")
    log("Final connection status:")
    return json.dumps(connection_status, indent=2)

if __name__ == "__main__":
    result = main()
    print(result)
