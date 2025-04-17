from flask import jsonify
import subprocess
from utils.logging import log


def api_paired_devices():
    try:
        devices = {}

        # Get list of all Bluetooth controllers
        list_output = subprocess.check_output(
            ["bluetoothctl", "list"],
            universal_newlines=True
        )

        controller_macs = []
        for line in list_output.splitlines():
            if line.startswith("Controller"):
                parts = line.strip().split()
                if len(parts) >= 2:
                    controller_macs.append(parts[1])

        # For each controller, list paired devices
        for ctrl_mac in controller_macs:
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            proc.stdin.write(f"select {ctrl_mac}\n")
            proc.stdin.write("devices Paired\n")
            proc.stdin.write("exit\n")
            proc.stdin.flush()

            try:
                output, _ = proc.communicate(timeout=7)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()

            for line in output.splitlines():
                if line.startswith("Device"):
                    parts = line.split()
                    if len(parts) >= 3:
                        mac = parts[1]
                        display_name = " ".join(parts[2:]).strip()
                        devices[mac] = display_name

        if not devices:
            return jsonify({"message": "No devices are paired."})

        return jsonify(devices)

    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        log(f"Error in /paired-devices endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500
