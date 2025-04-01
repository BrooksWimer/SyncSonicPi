#!/bin/bash
set -e

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

if [ "$#" -ne 4 ]; then
    log "Usage: $0 <configID> <configName> <speakersJson> <settingsJson>"
    exit 1
fi

CONFIG_ID="$1"
CONFIG_NAME="$2"
SPEAKERS_JSON="$3"
SETTINGS_JSON="$4"

log "Starting connection process for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)..."

#
# Read speakers (mac -> name) from JSON
#
declare -A speakers
while IFS=, read -r mac name; do
    speakers["$mac"]="$name"
done < <(echo "$SPEAKERS_JSON" | jq -r 'to_entries[] | "\(.key),\(.value)"')

#
# Read volumes and latencies (mac -> volume, latency) from JSON
#
declare -A volumes
declare -A latencies
while IFS=, read -r mac volume latency; do
    volumes["$mac"]="$volume"
    latencies["$mac"]="$latency"
done < <(echo "$SETTINGS_JSON" | jq -r 'to_entries[] | "\(.key),\(.value.volume),\(.value.latency)"')

#
# Discover Bluetooth controllers and record their paired/connected devices
#
controllers=()
declare -A pairedDevicesPerController
declare -A connectedDevicesPerController
declare -A speakerPort      # map speaker MAC -> controller MAC
declare -A portSpeaker      # map controller MAC -> speaker MAC (one-to-one usage)

while IFS= read -r line; do
    if [[ $line =~ Controller[[:space:]]([[:xdigit:]:]{17}) ]]; then
        ctrl_mac="${BASH_REMATCH[1]}"
        controllers+=("$ctrl_mac")
        log "Checking paired and connected devices for controller $ctrl_mac..."

        OUTPUT=$(bluetoothctl <<EOF
select $ctrl_mac
devices Paired
devices Connected
EOF
)
        log "--- Devices for controller $ctrl_mac ---"
        log "$OUTPUT"

        while IFS= read -r dev_line; do
            if [[ $dev_line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]] ]]; then
                mac="${BASH_REMATCH[1]}"
                # If the line also contains "Connected", store it as connected
                if [[ $dev_line == *"Connected"* ]]; then
                    connectedDevicesPerController["$ctrl_mac"]+=" $mac"
                    speakerPort["$mac"]="$ctrl_mac"
                    portSpeaker["$ctrl_mac"]="$mac"
                fi
                # Record as paired for this controller
                pairedDevicesPerController["$mac"]+=" $ctrl_mac"
            fi
        done <<< "$OUTPUT"
    fi
done < <(bluetoothctl list)

if [ ${#controllers[@]} -eq 0 ]; then
    log "No Bluetooth controllers found."
    exit 1
fi
log "Found controllers: ${controllers[@]}"

#
# Mark any controller that already has a connected device as 'used'
#
declare -A usedControllers
for ctrl in "${controllers[@]}"; do
    if [[ -n "${connectedDevicesPerController[$ctrl]}" ]]; then
        usedControllers["$ctrl"]=1
    fi
    # Also ensure speakerPort/portSpeaker reflect connected devices
    for dev_mac in ${connectedDevicesPerController[$ctrl]}; do
        speakerPort["$dev_mac"]="$ctrl"
        portSpeaker["$ctrl"]="$dev_mac"
    done
done

#
# Show which speakers are already connected
#
log "Connected speakers and ports:"
for mac in "${!speakerPort[@]}"; do
    log "Speaker $mac is connected on controller ${speakerPort[$mac]}"
done

#
# Remove any old virtual sink/loopback modules before proceeding
#
log "Unloading previous virtual sink and loopback modules..."
unload_virtual_modules() {
    local mods
    mods=$(pactl list short modules \
           | awk '{print $2 " " $1}' \
           | grep -E 'module-null-sink|module-loopback' \
           | awk '{print $2}')
    for mod in $mods; do
        log "Unloading module $mod"
        pactl unload-module "$mod" || true
    done
}
unload_virtual_modules

#
# Functions for waiting on Bluetooth states and for controlling bluetoothctl
#
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
wait_for_connection() { wait_for_status "$1" "Connected"; }
wait_for_trust() { wait_for_status "$1" "Trusted"; }
wait_for_pairing() { wait_for_status "$1" "Paired"; }

#
# Check if PulseAudio is running
#
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

#
# Load loopback from the virtual sink to each speaker’s sink
#
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

#
# Prepare a coproc for interactive bluetoothctl to reduce overhead
#
coproc BTCTL { bluetoothctl; }
sleep 2

send_bt_cmd() {
    local cmd="$1"
    echo "$cmd" >&"${BTCTL[1]}"
    # Collect a bit of output (non-blocking read)
    while read -t 0.5 -u "${BTCTL[0]}" line; do
        echo "$line"
    done
    sleep 1
}

#
# Pair/connect a single speaker on a particular controller
#
pair_speaker() {
    local speaker_name="$1"
    local speaker_mac="$2"
    local ctrl_mac="$3"

    log "Pairing \"$speaker_name\" ($speaker_mac) using controller $ctrl_mac..."
    send_bt_cmd "select $ctrl_mac"

    local did_scan=0
    # If not in that controller’s paired list, attempt a short scan
    if [[ " ${pairedDevicesPerController["$speaker_mac"]} " != *" $ctrl_mac "* ]]; then
        send_bt_cmd "scan on"
        did_scan=1
        sleep 5
    fi

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
    sleep 3

    # Confirm it shows as connected
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

    if [ "$did_scan" -eq 1 ]; then
        send_bt_cmd "scan off" || log "Warning: Failed to stop scanning."
    fi
    return 0
}

#
# Decide which controller is the best fit for a speaker
#
get_best_controller_for_speaker() {
    local mac="$1"
    # Prefer controllers where this speaker is already paired and not in use
    for ctrl in ${pairedDevicesPerController[$mac]}; do
        if [[ -z "${usedControllers[$ctrl]}" ]]; then
            echo "$ctrl"
            return
        fi
    done
    # Otherwise, use any unused controller
    for ctrl in "${controllers[@]}"; do
        if [[ -z "${usedControllers[$ctrl]}" ]]; then
            echo "$ctrl"
            return
        fi
    done
    echo ""
}

#
# Attempt to pair/connect each speaker in the configuration
#
for mac in "${!speakers[@]}"; do
    speaker_name="${speakers[$mac]}"

    # Skip if already connected
    if [[ -n "${speakerPort[$mac]}" ]]; then
        log "Speaker $speaker_name ($mac) is already connected on controller ${speakerPort[$mac]}. Skipping."
        continue
    fi

    ctrl_mac="$(get_best_controller_for_speaker "$mac")"
    if [[ -z "$ctrl_mac" ]]; then
        log "No available controller for $speaker_name ($mac). Skipping."
        continue
    fi

    # Ensure this controller does not already have a speaker assigned
    if [[ -n "${portSpeaker[$ctrl_mac]}" ]]; then
        log "Controller $ctrl_mac is already assigned to speaker ${portSpeaker[$ctrl_mac]}. Skipping $speaker_name ($mac)."
        continue
    fi

    log "Pair/Connect $speaker_name ($mac) on controller $ctrl_mac..."
    if pair_speaker "$speaker_name" "$mac" "$ctrl_mac"; then
        usedControllers["$ctrl_mac"]=1
        speakerPort["$mac"]="$ctrl_mac"
        portSpeaker["$ctrl_mac"]="$mac"
    else
        log "Failed to connect $speaker_name ($mac) on controller $ctrl_mac."
    fi
done

#
# Start PulseAudio, load our virtual sink, and loopbacks
#
pulseaudio --start || log "Warning: PulseAudio failed to start."
if ! wait_for_pulseaudio; then
    log "Error: PulseAudio did not initialize properly."
fi

log "Loading virtual sink module..."
VIRTUAL_SINK=$(pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out)
log "Virtual sink created with index: $VIRTUAL_SINK"
sleep 2

#
# (Optional) Example: skip loopback for a known phone MAC
#
KNOWN_PHONE_MAC="AC:DF:A1:52:8A:41"

for mac in "${!speakers[@]}"; do
    if [[ -n "${speakerPort[$mac]}" ]]; then
        sink_name="bluez_sink.${mac//:/_}.a2dp_sink"
        if [ "$mac" = "$KNOWN_PHONE_MAC" ]; then
            log "Detected phone ($mac). Skipping special sink creation for this device."
        else
            log "Loading loopback for sink: $sink_name"
            load_loopback "$sink_name"
        fi
    fi
done

log "Waking up all sinks..."
while IFS= read -r line; do
    sink_name=$(echo "$line" | awk '{print $2}')
    log "Unsuspending sink $sink_name..."
    pactl suspend-sink "$sink_name" 0
done < <(pactl list short sinks)

#
# Remove module-suspend-on-idle so our sinks don't automatically suspend
#
log "Unloading module-suspend-on-idle..."
for module in $(pactl list short modules | grep module-suspend-on-idle | awk '{print $1}'); do
    log "Unloading module-suspend-on-idle module $module"
    pactl unload-module "$module"
done

log "Connection process complete for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)."
