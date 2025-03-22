#!/bin/bash
set -e

#####################################################
# Usage check
#####################################################
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <configID> <configName> <speakersJson> <settingsJson>"
    exit 1
fi

CONFIG_ID="$1"
CONFIG_NAME="$2"
SPEAKERS_JSON="$3"
SETTINGS_JSON="$4"

echo "Starting connection process for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)..."

#####################################################
# Parse the speakers JSON into an associative array
#####################################################
declare -A speakers
while IFS=, read -r mac name; do
    speakers["$mac"]="$name"
done < <(echo "$SPEAKERS_JSON" | jq -r 'to_entries[] | "\(.key),\(.value)"')

#####################################################
# Parse the settings JSON (volume/latency)
#####################################################
declare -A volumes
declare -A latencies
while IFS=, read -r mac volume latency; do
    volumes["$mac"]="$volume"
    latencies["$mac"]="$latency"
done < <(echo "$SETTINGS_JSON" | jq -r 'to_entries[] | "\(.key),\(.value.volume),\(.value.latency)"')

#####################################################
# Discover Bluetooth controllers
#####################################################
controllers=()
while IFS= read -r line; do
    if [[ $line =~ Controller[[:space:]]([[:xdigit:]:]{17}) ]]; then
        controllers+=("${BASH_REMATCH[1]}")
    fi
done < <(bluetoothctl list)

if [ ${#controllers[@]} -eq 0 ]; then
    echo "No Bluetooth controllers found."
    exit 1
fi
echo "Found controllers: ${controllers[@]}"

#####################################################
# Collect paired and connected devices safely
#####################################################
declare -A pairedDevices
declare -A connectedDevices

for ctrl in "${controllers[@]}"; do
    echo "Checking devices for controller $ctrl..."

    # Paired devices
    PAIR_OUT=$(bluetoothctl <<EOF
select $ctrl
devices Paired
EOF
)
    while IFS= read -r line; do
        if [[ $line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]] ]]; then
            mac="${BASH_REMATCH[1]}"
            pairedDevices["$mac"]=1
        fi
    done <<< "$PAIR_OUT"

    # Connected devices
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

echo "Aggregated paired devices: ${!pairedDevices[@]}"
echo "Aggregated connected devices: ${!connectedDevices[@]}"

#####################################################
# Disconnect extraneous devices
#####################################################
for mac in "${!connectedDevices[@]}"; do
    if [ -z "${speakers[$mac]}" ]; then
        echo "Disconnecting extraneous device $mac (not part of configuration)..."
        bluetoothctl <<EOF
select ${controllers[0]}
disconnect $mac
EOF
        sleep 2
    fi
done

#####################################################
# Start bluetoothctl as a coprocess
#####################################################
coproc BTCTL { bluetoothctl; }
sleep 2  # Allow bluetoothctl to initialize

send_bt_cmd() {
    local cmd="$1"
    echo "$cmd" >&"${BTCTL[1]}"
    while read -t 0.5 -u "${BTCTL[0]}" line; do
        echo "$line"
    done
    sleep 1
}

#####################################################
# Pairing function with known-good timing
#####################################################
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

#####################################################
# Track which controllers are already in use
# so we only connect one speaker per adapter.
#####################################################
declare -A usedControllers

# Function to get the next free (unused) controller, or "" if none free
get_next_free_controller() {
    for ctrl in "${controllers[@]}"; do
        if [ -z "${usedControllers[$ctrl]}" ]; then
            echo "$ctrl"
            return 0
        fi
    done
    # If none free, return empty
    echo ""
}

#####################################################
# Main loop: For each speaker in the JSON config
#####################################################
for mac in "${!speakers[@]}"; do
    speaker_name="${speakers[$mac]}"
    echo "Processing speaker: $speaker_name ($mac)"

    # If speaker is already connected on ANY controller, skip
    if [ "${connectedDevices[$mac]}" == "1" ]; then
        echo "Speaker $speaker_name ($mac) is already connected on some port. Skipping."
        continue
    fi

    # Acquire the next free controller that hasn't been used
    ctrl_mac="$(get_next_free_controller)"
    if [ -z "$ctrl_mac" ]; then
        echo "No free controllers left! Skipping speaker $speaker_name ($mac)."
        continue
    fi

    # If speaker is already paired, just connect, else pair first
    if [ "${pairedDevices[$mac]}" == "1" ]; then
        echo "Speaker $speaker_name ($mac) is paired but not connected. Connecting via $ctrl_mac..."
        send_bt_cmd "select $ctrl_mac"
        sleep 2
        send_bt_cmd "connect $mac"
        sleep 5
    else
        echo "Speaker $speaker_name ($mac) is not paired. Running full pairing sequence on $ctrl_mac..."
        if ! pair_speaker "$speaker_name" "$mac" "$ctrl_mac"; then
            echo "Error: $speaker_name failed to connect."
        fi
    fi

    # If we got here, we attempted to connect on ctrl_mac.
    # Mark that controller as used.
    usedControllers["$ctrl_mac"]=1

done

# Stop scanning
send_bt_cmd "scan off"

#####################################################
# PulseAudio setup
#####################################################
pulseaudio --start

echo "Loading virtual sink module..."
VIRTUAL_SINK=$(pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out)
echo "Virtual sink created with index: $VIRTUAL_SINK"
sleep 2

# Create loopbacks from the virtual sink to each speaker
for mac in "${!speakers[@]}"; do
    sink_name="bluez_sink.${mac//:/_}.a2dp_sink"
    echo "Loading loopback for sink: $sink_name"
    LOOPBACK=$(pactl load-module module-loopback source=virtual_out.monitor sink="$sink_name" latency_msec=100 || true)
    if [[ "$LOOPBACK" =~ ^[0-9]+$ ]]; then
        echo "Loopback for $sink_name loaded with index: $LOOPBACK"
    else
        echo "Failure: Could not load loopback for $sink_name"
    fi
done

echo "Waking up all sinks..."
while IFS= read -r line; do
    sink_name=$(echo "$line" | awk '{print $2}')
    echo "Unsuspending sink $sink_name..."
    pactl suspend-sink "$sink_name" 0
done < <(pactl list short sinks)

echo "Unloading module-suspend-on-idle..."
for module in $(pactl list short modules | grep module-suspend-on-idle | awk '{print $1}'); do
    echo "Unloading module-suspend-on-idle module $module"
    pactl unload-module "$module"
done

echo "Connection process complete for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)."
