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

# Timeouts and delays (in seconds)
TIMEOUT=10
PAIR_ATTEMPT_DELAY=2

# Start bluetoothctl as a persistent coprocess.
coproc BTCTL { bluetoothctl; }
sleep 2  # Allow bluetoothctl to initialize

# Helper: send command to bluetoothctl and display output
send_bt_cmd() {
    local cmd="$1"
    echo "$cmd" >&"${BTCTL[1]}"
    # Read and print available output (with a short timeout)
    while read -t 0.5 -u "${BTCTL[0]}" line; do
        echo "$line"
    done
    sleep 1
}

# Function to do a full pairing sequence
pair_speaker() {
    local speaker_name="$1"
    local speaker_mac="$2"
    local ctrl_mac="$3"

    echo "Pairing \"$speaker_name\" ($speaker_mac) using controller $ctrl_mac..."
    send_bt_cmd "select $ctrl_mac"
    sleep 2

    send_bt_cmd "scan on"
    sleep 5

    send_bt_cmd "pair $speaker_mac"
    sleep 3

    send_bt_cmd "trust $speaker_mac"
    sleep 3

    send_bt_cmd "connect $speaker_mac"
    sleep 5

    return 0
}

echo "Starting pairing process for selected speakers..."

# Clean up existing sink and loopback modules to avoid interference.
echo "Cleaning up existing sink and loopback modules..."
for module in $(pactl list short modules | grep -E 'module-null-sink|module-loopback' | awk '{print $1}'); do
    echo "Unloading module $module..."
    pactl unload-module "$module" || echo "Module $module not found, skipping..."
done

###########################################################################
# Gather Paired and Connected devices across all controllers (optimization)
###########################################################################
declare -A pairedDevices
declare -A connectedDevices

echo "Gathering paired/connected info from controllers..."
for ctrl in "${controllers[@]}"; do
    # Paired
    PAIR_OUT=$(bluetoothctl <<EOF
select $ctrl
devices Paired
EOF
)
    while IFS= read -r line; do
        # Ex: "Device 00:11:22:33:44:55 SpeakerName"
        if [[ $line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]] ]]; then
            mac="${BASH_REMATCH[1]}"
            pairedDevices["$mac"]=1
        fi
    done <<< "$PAIR_OUT"

    # Connected
    CONN_OUT=$(bluetoothctl <<EOF
select $ctrl
devices Connected
EOF
)
    while IFS= read -r line; do
        if [[ $line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]] ]]; then
            mac="${BASH_REMATCH[1]}"
            connectedDevices["$mac"]=1
        fi
    done <<< "$CONN_OUT"
done

echo "Paired devices detected: ${!pairedDevices[@]}"
echo "Connected devices detected: ${!connectedDevices[@]}"

################################################################
# Pair each selected speaker using controllers in round-robin,
# but skip if already connected, or just connect if already paired.
################################################################
i=0
for mac in "${!speakers[@]}"; do
    speaker_name="${speakers[$mac]}"

    echo "---------------------------------------------"
    echo "Processing $speaker_name ($mac)..."

    # If already connected anywhere, skip
    if [ "${connectedDevices[$mac]}" == "1" ]; then
        echo "Speaker $speaker_name ($mac) is already connected. Skipping."
        continue
    fi

    # Round-robin approach to pick a controller
    ctrl_index=$(( i % ${#controllers[@]} ))
    ctrl_mac="${controllers[$ctrl_index]}"

    # If it's paired but not connected, just connect
    if [ "${pairedDevices[$mac]}" == "1" ]; then
        echo "Speaker $speaker_name ($mac) is paired but not connected. Connecting..."
        send_bt_cmd "select $ctrl_mac"
        sleep 2
        send_bt_cmd "connect $mac"
        sleep 5
    else
        # Not paired, do the full pairing
        if ! pair_speaker "$speaker_name" "$mac" "$ctrl_mac"; then
            echo "Error: $speaker_name failed to complete all steps. Please try again."
        fi
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
    sink_name="bluez_sink.${mac//:/_}.a2dp_sink"
    echo "Loading loopback for sink: $sink_name"
    LOOPBACK=$(pactl load-module module-loopback source=virtual_out.monitor sink="$sink_name" latency_msec=100)
    echo "Loopback module for $sink_name loaded with index: $LOOPBACK"
done

echo "Waking up all sinks..."
while IFS= read -r line; do
    # Each line from pactl list short sinks: ID    SinkName    Driver ... State
    sink_name=$(echo "$line" | awk '{print $2}')
    echo "Unsuspending sink $sink_name..."
    pactl suspend-sink "$sink_name" 0
done < <(pactl list short sinks)

echo "Unloading module-suspend-on-idle..."
for module in $(pactl list short modules | grep module-suspend-on-idle | awk '{print $1}'); do
    echo "Unloading module-suspend-on-idle module $module..."
    pactl unload-module "$module"
done

echo "Startup configuration complete."
