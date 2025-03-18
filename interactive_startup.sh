#!/bin/bash
set -e

# Preconfigured speakers: Speaker Name → MAC Address
declare -A speakers
while IFS=, read -r mac name; do
    speakers["$name"]="$mac"
done < selected_devices.txt


# Preconfigured Bluetooth controllers (MAC addresses from bluetoothctl list)
controllers=("2C:CF:67:CE:57:91" "BC:FC:E7:21:1A:0B")

# Timeouts and delays (in seconds)
TIMEOUT=30                   # for waiting steps (trusting/connecting)
PAIR_RETRY_DURATION=20       # how long to try pairing repeatedly
INITIAL_SCAN_WAIT=30         # time to wait after turning scanning on
PAIR_ATTEMPT_DELAY=3         # delay between repeated pair attempts

# Start bluetoothctl as a persistent coprocess.
coproc BTCTL { bluetoothctl; }
sleep 2  # Allow bluetoothctl to initialize

# Function to send a command to the persistent bluetoothctl session.
send_bt_cmd() {
    local cmd="$1"
    echo "$cmd" >&"${BTCTL[1]}"
    while read -t 0.5 -u "${BTCTL[0]}" line; do
        echo "$line"
    done
    sleep 1
	# Give a little time for the command to process.
}

# Function to wait for a status (via "bluetoothctl info") to appear.
wait_for_status() {
    local speaker_mac="$1"
    local status_text="$2"
    local step_name="$3"
    echo "Waiting for $step_name for device $speaker_mac..."
    for ((i=0; i<TIMEOUT; i++)); do
        if bluetoothctl info "$speaker_mac" | grep -q "$status_text"; then
            echo "$step_name achieved for device $speaker_mac."
            return 0
        fi
        sleep 1
    done
    echo "Timeout waiting for $step_name for device $speaker_mac."
    return 1
}

# Function to clear all paired devices for a given controller.
clear_paired_devices() {
    local ctrl_mac="$1"
    echo "Clearing paired devices for controller $ctrl_mac..."
    
    send_bt_cmd "select $ctrl_mac"
    sleep 1

    # Get the current list of devices (using a separate call)
    devices=$(bluetoothctl devices)
    while read -r line; do
        device_mac=$(echo "$line" | awk '{print $2}')
        if [ -n "$device_mac" ]; then
            echo "Removing device: $device_mac from controller $ctrl_mac"
            send_bt_cmd "remove $device_mac"
            sleep 1
        fi
    done < <(echo "$devices" | grep '^Device')
    
    echo "Cleared paired devices for controller $ctrl_mac."
}

# Function to pair a speaker with a specific controller.
pair_speaker() {
    local speaker_name="$1"
    local speaker_mac="$2"
    local ctrl_mac="$3"

    echo "Pairing \"$speaker_name\" ($speaker_mac) using controller $ctrl_mac..."

    # Select the controller and initialize the agent.
    send_bt_cmd "select $ctrl_mac"
    sleep 2

    # Now turn scanning on (separately) and wait a bit.
    send_bt_cmd "scan on"
    echo "Waiting $INITIAL_SCAN_WAIT seconds for scanning to pick up the device..."
    sleep "$INITIAL_SCAN_WAIT"

    # Repeatedly attempt to pair for PAIR_RETRY_DURATION seconds.
    local paired=0
    local start_time
    start_time=$(date +%s)
    while true; do
        send_bt_cmd "pair $speaker_mac"
        if bluetoothctl info "$speaker_mac" | grep -q "Paired: yes"; then
            paired=1
            echo "Device $speaker_mac paired."
            break
        fi
        sleep "$PAIR_ATTEMPT_DELAY"
        local now
        now=$(date +%s)
        if (( now - start_time >= PAIR_RETRY_DURATION )); then
            break
        fi
    done

    # Turn scanning off.
    send_bt_cmd "scan off"

    if [ $paired -ne 1 ]; then
        echo "Error: Device $speaker_mac did not pair within $PAIR_RETRY_DURATION seconds."
        return 1
    fi

    # Trust the device.
    send_bt_cmd "trust $speaker_mac"
    if ! wait_for_status "$speaker_mac" "Trusted: yes" "Trusting"; then
        echo "Error: Device $speaker_mac did not get trusted."
        return 1
    fi

    # Connect the device.
    send_bt_cmd "connect $speaker_mac"
    if ! wait_for_status "$speaker_mac" "Connected: yes" "Connecting"; then
        echo "Error: Device $speaker_mac did not connect."
        return 1
    fi

    echo "\"$speaker_name\" successfully paired, trusted, and connected on controller $ctrl_mac."
    return 0
}

echo "Starting Bluetooth pairing process for preconfigured speakers..."

# Clear paired devices on each controller.
for ctrl in "${controllers[@]}"; do
    clear_paired_devices "$ctrl"
done

# Loop over speakers (cycling through the controllers).
i=0
for speaker in "${!speakers[@]}"; do
    ctrl_index=$(( i % ${#controllers[@]} ))
    ctrl_mac="${controllers[$ctrl_index]}"
    echo "---------------------------------------------"
    echo "Please turn on \"$speaker\" and put it in pairing mode for controller $ctrl_mac."
    read -p "Press [Enter] once \"$speaker\" is ready: "
    if ! pair_speaker "$speaker" "${speakers[$speaker]}" "$ctrl_mac"; then
        echo "Error: \"$speaker\" failed to complete all steps. Please try again."
    fi
    i=$((i+1))
done

echo "All speakers pairing attempted."

# Allow time for Bluetooth sinks to register.
sleep 5

# Start PulseAudio (if not running) and set up the virtual sink/loopback.
pulseaudio --start
echo "Loading virtual sink module..."
VIRTUAL_SINK=$(pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out)
echo "Virtual sink created with index: $VIRTUAL_SINK"
sleep 2

# For each speaker, load a loopback from the virtual sink monitor to the Bluetooth sink.
for speaker in "${!speakers[@]}"; do
    speaker_mac="${speakers[$speaker]}"
    # Expect the Bluetooth sink to be named in the form: bluez_output.<MAC_with_underscores>.1
    sink_name="bluez_output.${speaker_mac//:/_}.1"
    echo "Loading loopback for sink: $sink_name"
    LOOPBACK=$(pactl load-module module-loopback source=virtual_out.monitor sink="$sink_name" latency_msec=100)
    echo "Loopback module for $sink_name loaded with index: $LOOPBACK"
done

echo "Startup configuration complete."
