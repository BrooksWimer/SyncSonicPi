#!/bin/bash
set -e

#####################################################
# Logging Function
#####################################################
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

#####################################################
# Usage check
#####################################################
if [ "$#" -ne 4 ]; then
    log "Usage: $0 <configID> <configName> <speakersJson> <settingsJson>"
    exit 1
fi

CONFIG_ID="$1"
CONFIG_NAME="$2"
SPEAKERS_JSON="$3"
SETTINGS_JSON="$4"

log "Starting connection process for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)..."

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
    log "No Bluetooth controllers found."
    exit 1
fi
log "Found controllers: ${controllers[@]}"

#####################################################
# Build mapping for connected devices and ports
# speakerPort: maps speaker MAC to the controller port it's connected on
# portSpeaker: maps a controller port to the speaker MAC already connected
#####################################################
declare -A speakerPort
declare -A portSpeaker

for ctrl in "${controllers[@]}"; do
    log "Checking devices for controller $ctrl..."
    # Connected devices per controller
    CONN_OUT=$(bluetoothctl <<EOF
select $ctrl
devices Connected
EOF
)
    while IFS= read -r line; do
        if [[ $line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]] ]]; then
            mac="${BASH_REMATCH[1]}"
            # If the connected device is not in the provided speakers list, disconnect it.
            if [ -z "${speakers[$mac]}" ]; then
                log "Speaker $mac is connected on controller $ctrl but is not in the configuration. Disconnecting..."
                bluetoothctl <<EOF
select $ctrl
disconnect $mac
EOF
                sleep 2
            else
                # If speaker already exists on another port, disconnect it from this one.
                if [ -n "${speakerPort[$mac]}" ]; then
                    log "Speaker $mac is connected on multiple ports (${speakerPort[$mac]} and $ctrl). Disconnecting from controller $ctrl."
                    bluetoothctl <<EOF
select $ctrl
disconnect $mac
EOF
                    sleep 2
                else
                    speakerPort["$mac"]="$ctrl"
                    portSpeaker["$ctrl"]="$mac"
                fi
            fi
        fi
    done <<< "$CONN_OUT"
done

log "Connected speakers and ports:"
for mac in "${!speakerPort[@]}"; do
    log "Speaker $mac is connected on controller ${speakerPort[$mac]}"
done

#####################################################
# Unload previous virtual sink and loopback modules
#####################################################
unload_virtual_modules() {
    local mods
    mods=$(pactl list short modules | awk '{print $2 " " $1}' | grep -E 'module-null-sink|module-loopback' | awk '{print $2}')
    for mod in $mods; do
        log "Unloading module $mod"
        pactl unload-module "$mod" || true
    done
}

log "Unloading previous virtual sink and loopback modules..."
unload_virtual_modules

#####################################################
# Helper functions to wait for device status changes
#####################################################
wait_for_status() {
    local mac="$1"
    local status_keyword="$2"
    local timeout="${3:-30}"
    local interval=2
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if bluetoothctl info "$mac" 2>/dev/null | grep -q "$status_keyword: yes"; then
            log "Device $mac status '$status_keyword' confirmed."
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed+interval))
    done
    log "Timeout waiting for device $mac to become $status_keyword."
    return 1
}

wait_for_connection() {
    wait_for_status "$1" "Connected"
}

wait_for_trust() {
    wait_for_status "$1" "Trusted"
}

wait_for_pairing() {
    wait_for_status "$1" "Paired"
}

#####################################################
# Function to wait for PulseAudio to start
#####################################################
wait_for_pulseaudio() {
    local timeout=20
    local interval=2
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if pactl info >/dev/null 2>&1; then
            log "PulseAudio is running."
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed+interval))
    done
    log "PulseAudio did not start in time."
    return 1
}

#####################################################
# Function to load loopback module with retry logic
#####################################################
load_loopback() {
    local sink_name="$1"
    local attempt=1
    local max_attempts=3
    local loopback
    while [ $attempt -le $max_attempts ]; do
        loopback=$(pactl load-module module-loopback source=virtual_out.monitor sink="$sink_name" latency_msec=100 2>/dev/null || true)
        if [[ "$loopback" =~ ^[0-9]+$ ]]; then
            log "Loopback for $sink_name loaded with index: $loopback"
            return 0
        else
            log "Attempt $attempt: Failure loading loopback for $sink_name. Retrying..."
            sleep 2
        fi
        attempt=$((attempt+1))
    done
    log "Failure: Could not load loopback for $sink_name after $max_attempts attempts."
    return 1
}

#####################################################
# Start bluetoothctl as a coprocess
#####################################################
coproc BTCTL { bluetoothctl; }
sleep 2  # Allow bluetoothctl to initialize

send_bt_cmd() {
    local cmd="$1"
    echo "$cmd" >&"${BTCTL[1]}"
    # Read any immediate output for a short period
    while read -t 0.5 -u "${BTCTL[0]}" line; do
        echo "$line"
    done
    sleep 1
}

#####################################################
# Pairing function with improved timing and status checks
# This function always issues pair and trust commands on the selected controller.
#####################################################
pair_speaker() {
    local speaker_name="$1"
    local speaker_mac="$2"
    local ctrl_mac="$3"

    log "Pairing \"$speaker_name\" ($speaker_mac) using controller $ctrl_mac..."
    send_bt_cmd "select $ctrl_mac"

    send_bt_cmd "scan on"
    sleep 5

    send_bt_cmd "pair $speaker_mac"
    if ! wait_for_pairing "$speaker_mac"; then
        log "Error: Pairing failed for $speaker_name ($speaker_mac)."
        return 1
    fi

    send_bt_cmd "trust $speaker_mac"
    if ! wait_for_trust "$speaker_mac"; then
        log "Error: Trust command failed for $speaker_name ($speaker_mac)."
        return 1
    fi

    send_bt_cmd "connect $speaker_mac"
    # Wait a few seconds to let connection settle
    sleep 3
    # Now verify the connection by checking "devices Connected" on the selected controller
    local connected_devices
    connected_devices=$(bluetoothctl <<EOF
select $ctrl_mac
devices Connected
EOF
)
    if echo "$connected_devices" | grep -q "$speaker_mac"; then
        log "Speaker $speaker_mac confirmed in connected devices list on controller $ctrl_mac."
    else
        log "Error: Speaker $speaker_mac did not appear in connected devices list on controller $ctrl_mac."
        return 1
    fi

    return 0
}

#####################################################
# Track which controllers (ports) are already used
#####################################################
declare -A usedControllers
# Initially mark controllers that already have a connected speaker as used.
for ctrl in "${controllers[@]}"; do
    if [ -n "${portSpeaker[$ctrl]}" ]; then
        usedControllers["$ctrl"]=1
    fi
done

# Function to get the next free controller that is not already used.
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
# Skip speakers that are already connected on any controller.
#####################################################
for mac in "${!speakers[@]}"; do
    speaker_name="${speakers[$mac]}"

    # If the speaker is already connected on any port, skip it
    if [ -n "${speakerPort[$mac]}" ]; then
        log "Speaker $speaker_name ($mac) is already connected on controller ${speakerPort[$mac]}. Skipping."
        continue
    fi

    log "Processing speaker: $speaker_name ($mac)"

    # Acquire the next free controller that hasn't been used
    ctrl_mac="$(get_next_free_controller)"
    if [ -z "$ctrl_mac" ]; then
        log "No free controllers left! Skipping speaker $speaker_name ($mac)."
        continue
    fi

    # Run the pairing sequence (which will ensure the speaker is paired/trusted/connected on this controller)
    log "Running pairing sequence for speaker $speaker_name ($mac) on controller $ctrl_mac..."
    if ! pair_speaker "$speaker_name" "$mac" "$ctrl_mac"; then
        log "Error: $speaker_name ($mac) failed to connect on controller $ctrl_mac."
    else
        # Mark this controller as used and record the connection.
        usedControllers["$ctrl_mac"]=1
        speakerPort["$mac"]="$ctrl_mac"
        portSpeaker["$ctrl_mac"]="$mac"
    fi
done

#####################################################
# Stop scanning safely
#####################################################
send_bt_cmd "scan off" || log "Warning: Failed to stop scanning."

#####################################################
# PulseAudio setup
#####################################################
pulseaudio --start || log "Warning: PulseAudio failed to start."
if ! wait_for_pulseaudio; then
    log "Error: PulseAudio did not initialize properly."
fi

log "Loading virtual sink module..."
VIRTUAL_SINK=$(pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out)
log "Virtual sink created with index: $VIRTUAL_SINK"
sleep 2

#####################################################
# Create loopbacks from the virtual sink to each speaker's sink
#####################################################
for mac in "${!speakers[@]}"; do
    # Only create a loopback if the speaker ended up connected
    if [ -n "${speakerPort[$mac]}" ]; then
        sink_name="bluez_sink.${mac//:/_}.a2dp_sink"
        log "Loading loopback for sink: $sink_name"
        load_loopback "$sink_name"
    fi
done

#####################################################
# Unsuspend all sinks
#####################################################
log "Waking up all sinks..."
while IFS= read -r line; do
    sink_name=$(echo "$line" | awk '{print $2}')
    log "Unsuspending sink $sink_name..."
    pactl suspend-sink "$sink_name" 0
done < <(pactl list short sinks)

#####################################################
# Unload module-suspend-on-idle
#####################################################
log "Unloading module-suspend-on-idle..."
for module in $(pactl list short modules | grep module-suspend-on-idle | awk '{print $1}'); do
    log "Unloading module-suspend-on-idle module $module"
    pactl unload-module "$module"
done

log "Connection process complete for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)."
