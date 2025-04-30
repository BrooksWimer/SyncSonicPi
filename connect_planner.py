from utils.logging import log
import os

reserved = os.getenv("RESERVED_HCI")
if not reserved:
    raise RuntimeError("RESERVED_HCI not set – cannot pick phone adapter")

def connect_one_plan(target_mac: str, allowed_macs: list[str], objects: dict) -> tuple[str, str, list[tuple[str, str]]]:
    """
    Determines the appropriate connection plan for a given target device:
    - If already connected correctly, returns 'already_connected'.
    - If needs connection and a controller is available, returns 'needs_connection'.
    - If no suitable controllers are available, returns 'error'.

    Args:
        target_mac (str): The MAC address of the target device.
        allowed_macs (list[str]): The list of allowed speaker MACs.
        objects (dict): The D-Bus object tree from GetManagedObjects().

    Returns:
        tuple[str, str, list[tuple[str, str]]]:
            - Status string ('already_connected', 'needs_connection', or 'error')
            - Controller MAC address to use (if applicable)
            - List of (device_mac, controller_mac) tuples to disconnect
    """
    target_mac = target_mac.upper()
    allowed_macs = [mac.upper() for mac in allowed_macs]
    disconnect_list = []
    target_connected_on = []
    config_speaker_usage = {}
    used_controllers = set()
    adapters = {}

    # Build a map of adapter MACs to their object paths
    for path, ifaces in objects.items():
        if "org.bluez.Adapter1" in ifaces:
            addr = ifaces["org.bluez.Adapter1"].get("Address", "").upper()
            hci_name = path.split("/")[-1]
            if hci_name == reserved:
                continue  # Skip reserved adapter
            adapters[addr] = path

    log(f"Planning connection for target: {target_mac}")
    log(f"Allowed MACs in config: {allowed_macs}")

    # Analyze all devices
    for path, ifaces in objects.items():
        dev = ifaces.get("org.bluez.Device1")
        if not dev:
            continue
        dev_mac = dev.get("Address", "").upper()
        adapter_prefix = "/".join(path.split("/")[:4])

        ctrl_mac = None
        for mac, adapter_path in adapters.items():
            if adapter_prefix == adapter_path:
                ctrl_mac = mac
                break

        if not ctrl_mac:
            continue  # This device does not belong to a recognized adapter

        if dev.get("Connected", False):
            log(f"Found connected device: {dev_mac} on {ctrl_mac}")

            if dev_mac in allowed_macs:
                config_speaker_usage.setdefault(dev_mac, []).append(ctrl_mac)

            if dev_mac == target_mac:
                target_connected_on.append(ctrl_mac)
                log(f"Target {dev_mac} already connected on {ctrl_mac}")

            elif dev_mac not in allowed_macs:
                disconnect_list.append((dev_mac, ctrl_mac))
                log(f"Out-of-config device {dev_mac} → marked for disconnection")

            elif dev_mac in allowed_macs:
                used_controllers.add(ctrl_mac)
                log(f"Config speaker {dev_mac} occupies controller {ctrl_mac}")

    log(f"Target is currently connected on: {target_connected_on}")
    log(f"Disconnect list built: {disconnect_list}")
    log(f"Controllers in use by config devices: {used_controllers}")

    # Handle multiple connections of target
    if len(target_connected_on) > 1:
        controller_to_keep = target_connected_on[0]
        for ctrl_mac in target_connected_on[1:]:
            disconnect_list.append((target_mac, ctrl_mac))
        log(f"Target connected on multiple controllers, keeping {controller_to_keep}, disconnecting others")
        return "already_connected", controller_to_keep, disconnect_list

    # Target connected once: ensure it's not sharing with another config speaker
    if len(target_connected_on) == 1:
        controller = target_connected_on[0]
        for mac, controllers in config_speaker_usage.items():
            if mac != target_mac and controller in controllers:
                disconnect_list.append((target_mac, controller))
                log(f"Target {target_mac} shares controller {controller} with config speaker {mac}, reallocating")

                # Try to find a free controller
                for new_ctrl_mac in adapters:
                    if new_ctrl_mac not in used_controllers and new_ctrl_mac != controller:
                        log(f"Assigning free controller {new_ctrl_mac} to target {target_mac}")
                        return "needs_connection", new_ctrl_mac, disconnect_list

                # Fallback: free a duplicate
                for mac2, controllers2 in config_speaker_usage.items():
                    if len(controllers2) > 1:
                        ctrl_to_free = controllers2[1]
                        disconnect_list.append((mac2, ctrl_to_free))
                        log(f"Freeing {ctrl_to_free} from {mac2} to connect target {target_mac}")
                        return "needs_connection", ctrl_to_free, disconnect_list

                log(f"No controller available after rebalance for target {target_mac}")
                return "error", "", disconnect_list

        return "already_connected", controller, disconnect_list

    # Target is not currently connected anywhere
    for ctrl_mac in adapters:
        if ctrl_mac not in used_controllers:
            log(f"Free controller {ctrl_mac} found for target {target_mac}")
            return "needs_connection", ctrl_mac, disconnect_list

    for mac, controllers in config_speaker_usage.items():
        if len(controllers) > 1:
            ctrl_to_free = controllers[1]
            disconnect_list.append((mac, ctrl_to_free))
            log(f"Freeing controller {ctrl_to_free} from {mac} to connect target {target_mac}")
            return "needs_connection", ctrl_to_free, disconnect_list

    log(f"No available controller found for target {target_mac}")
    return "error", "", disconnect_list