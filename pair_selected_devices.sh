#!/bin/bash
set -e

# Read selected devices from selected_devices.txt.
# Each line should be: MAC,DisplayName
declare -A speakers
while IFS=, read -r mac name; do
    speakers["$mac"]="$name"
done < selected_devices.txt

# Preconfigured Bluetooth controllers (MAC addresses from bluetoothctl list)
controllers=("BC:FC:E7:21:21:C6" "2C:CF:67:CE:57:91" "BC:FC:E7:21:1A:0B")

# Timeouts and delays (in seconds) – reduced from 30 to 10 seconds
TIMEOUT=10                   # For waiting steps (trusting/connecting)
PAIR_ATTEMPT_DELAY=2         # Delay between repeated pair attempts

# Start bluetoothctl as a persistent coprocess.
coproc BTCTL { bluetoothctl; }
sleep 2  # Allow bluetoothctl to initialize

# Function to send a command to the persistent bluetoothctl session and print output.
send_bt_cmd() {
    local cmd="$1"
    echo "$cmd" >&"${BTCTL[1]}"
    # Read and print available output (with a short timeout)
    while read -t 0.5 -u "${BTCTL[0]}" line; do
        echo "$line"
    done
    sleep 1
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

    
    send_bt_cmd "pair $speaker_mac"
    
    sleep 3

    send_bt_cmd "trust $speaker_mac"
    
    sleep 3

    send_bt_cmd "connect $speaker_mac"

    return 0
}

echo "Starting pairing process for selected speakers..."


# Clean up existing sink and loopback modules to avoid interference.
echo "Cleaning up existing sink and loopback modules..."
for module in $(pactl list short modules | grep -E 'module-null-sink|module-loopback' | awk '{print $1}'); do
    echo "Unloading module $module..."
    pactl unload-module "$module" || echo "Module $module not found, skipping..."
done


# Pair each selected speaker using controllers in round-robin.
i=0
for mac in "${!speakers[@]}"; do
    speaker_name="${speakers[$mac]}"
    ctrl_index=$(( i % ${#controllers[@]} ))
    ctrl_mac="${controllers[$ctrl_index]}"
    echo "---------------------------------------------"
    echo "Pairing $speaker_name ($mac) using controller $ctrl_mac..."
    if ! pair_speaker "$speaker_name" "$mac" "$ctrl_mac"; then
        echo "Error: $speaker_name failed to complete all steps. Please try again."
    fi
    i=$((i+1))
done

echo "All selected speakers pairing attempted."


send_bt_cmd "scan off"

# Start PulseAudio (if not running) and set up the virtual sink/loopback.
pulseaudio --start
echo "Loading virtual sink module..."
VIRTUAL_SINK=$(pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out)
echo "Virtual sink created with index: $VIRTUAL_SINK"
sleep 2

# For each speaker, load a loopback from the virtual sink monitor to the Bluetooth sink.
for mac in "${!speakers[@]}"; do
    # Use the MAC address directly.
    sink_name="bluez_sink.${mac//:/_}.a2dp_sink"
    echo "Loading loopback for sink: $sink_name"
    LOOPBACK=$(pactl load-module module-loopback source=virtual_out.monitor sink="$sink_name" latency_msec=100)
    echo "Loopback module for $sink_name loaded with index: $LOOPBACK"
done


# Unsuspend all sinks by iterating through them.
echo "Waking up all sinks..."
while IFS= read -r line; do
    # Each line from pactl list short sinks: ID    SinkName    Driver ... State
    sink_name=$(echo "$line" | awk '{print $2}')
    echo "Unsuspending sink $sink_name..."
    pactl suspend-sink "$sink_name" 0
done < <(pactl list short sinks)

# Unload module-suspend-on-idle to prevent auto-suspension.
echo "Unloading module-suspend-on-idle..."
for module in $(pactl list short modules | grep module-suspend-on-idle | awk '{print $1}'); do
    echo "Unloading module-suspend-on-idle module $module..."
    pactl unload-module "$module"
done


echo "Startup configuration complete."
