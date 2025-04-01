#!/usr/bin/env bash
set -e

###########################################################################
# Logging helper
###########################################################################
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

###########################################################################
# Wait functions (polling using bluetoothctl info)
###########################################################################
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
wait_for_pairing() { wait_for_status "$1" "Paired"; }
wait_for_trust()    { wait_for_status "$1" "Trusted"; }
wait_for_connection() { wait_for_status "$1" "Connected"; }

###########################################################################
# Wait for PulseAudio to start (unchanged)
###########################################################################
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

###########################################################################
# Function to load loopback module with retry logic (unchanged)
###########################################################################
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

###########################################################################
# Start bluetoothctl as a coprocess (unchanged)
###########################################################################
coproc BTCTL { bluetoothctl; }
sleep 2  # Allow bluetoothctl to initialize

###########################################################################
# Enhanced send_bt_cmd: send command and wait for the prompt to appear.
# We assume the prompt looks like "[... ]#" at the start of a line.
###########################################################################
send_bt_cmd() {
    local cmd="$1"
    echo "$cmd" >&"${BTCTL[1]}"
    # Read any immediate output for a short period
    while read -t 0.5 -u "${BTCTL[0]}" line; do
        echo "$line"
    done
    sleep 3
}
###########################################################################
# Revised pair_speaker: uses enhanced send_bt_cmd to ensure sequential commands.
###########################################################################
pair_speaker() {
    local speaker_name="$1"
    local speaker_mac="$2"
    local ctrl_mac="$3"

    log "Pairing \"$speaker_name\" ($speaker_mac) using controller $ctrl_mac..."
    send_bt_cmd "select $ctrl_mac"
    send_bt_cmd "scan on"
    sleep 5

    send_bt_cmd "pair $speaker_mac"
    if ! bluetoothctl info "$speaker_mac" 2>/dev/null | grep -q "Paired: yes"; then
        if ! wait_for_pairing "$speaker_mac"; then
            log "Error: Pairing failed for $speaker_name ($speaker_mac)."
            return 1
        fi
    else
        log "Device $speaker_mac already paired."
    fi

    send_bt_cmd "trust $speaker_mac"
    if ! wait_for_trust "$speaker_mac"; then
        log "Error: Trust command failed for $speaker_name ($speaker_mac)."
        return 1
    fi

    send_bt_cmd "connect $speaker_mac"
    sleep 3
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

    send_bt_cmd "scan off" || log "Warning: Failed to stop scanning."
    return 0
}

###########################################################################
# Revised connect_only: uses enhanced send_bt_cmd for sequential commands.
###########################################################################
connect_only() {
    local speaker_mac="$1"
    local speaker_name="$2"
    local ctrl_mac="$3"
    
    log "Connecting $speaker_name ($speaker_mac) on controller $ctrl_mac..."
    send_bt_cmd "select $ctrl_mac"
    send_bt_cmd "scan on"
    sleep 5
    send_bt_cmd "scan off" || log "Warning: Failed to stop scanning."
    send_bt_cmd "connect $speaker_mac"
    sleep 3
    local connected_devices
    connected_devices=$(bluetoothctl <<EOF
select $ctrl_mac
devices Connected
EOF
)
    if echo "$connected_devices" | grep -q "$speaker_mac"; then
        log "Successfully connected $speaker_name ($speaker_mac) on controller $ctrl_mac."
        return 0
    else
        log "Error: $speaker_name ($speaker_mac) did not appear as connected on controller $ctrl_mac."
        return 1
    fi
}

###########################################################################
# Disconnect a device from a given controller.
###########################################################################
disconnect_device() {
    local speaker_mac="$1"
    local ctrl_mac="$2"
    log "Disconnecting $speaker_mac from controller $ctrl_mac..."
    send_bt_cmd "select $ctrl_mac"
    send_bt_cmd "disconnect $speaker_mac"
    sleep 2
}

###########################################################################
# Main: Process gameplan JSON input and apply connection flow.
#
# Usage: ./apply_gameplan.sh <gameplan.json>
#
# The gameplan JSON is expected to be structured as:
# {
#   "<sp_mac>": {
#       "name": "...",
#       "paired_on": [ ... ],
#       "connected_on": [ ... ],
#       "disconnect": [ ... ],
#       "action": "..."
#   },
#   ...
# }
###########################################################################
if [ "$#" -ne 1 ]; then
    log "Usage: $0 <gameplan.json>"
    exit 1
fi

GAMEPLAN_INPUT="$1"
if [ -f "$GAMEPLAN_INPUT" ]; then
    gameplan_json=$(cat "$GAMEPLAN_INPUT")
else
    gameplan_json="$GAMEPLAN_INPUT"
fi

log "Applying gameplan..."

# Process each target speaker in the gameplan.
for sp_mac in $(echo "$gameplan_json" | jq -r 'keys[]'); do
    sp_name=$(echo "$gameplan_json" | jq -r --arg sp "$sp_mac" '.[$sp].name')
    action=$(echo "$gameplan_json" | jq -r --arg sp "$sp_mac" '.[$sp].action')
    disconnect_list=$(echo "$gameplan_json" | jq -r --arg sp "$sp_mac" '.[$sp].disconnect | join(",")')
    
    log "Processing $sp_name ($sp_mac) with action: $action"
    
    # Disconnect from any controllers in the disconnect list.
    IFS=',' read -ra dlist <<< "$disconnect_list"
    for ctrl in "${dlist[@]}"; do
        ctrl=$(echo "$ctrl" | xargs)
        if [ -n "$ctrl" ]; then
            disconnect_device "$sp_mac" "$ctrl"
        fi
    done
    
    # Extract the recommended controller from the action text.
    rec_ctrl=$(echo "$action" | grep -oE "controller [^ )\"]+" | awk '{print $2}')
    
    if [[ "$action" == No\ action* ]]; then
        log "$sp_name ($sp_mac) already connected. Skipping connection."
        continue
    elif [[ "$action" == *"Pair and connect"* ]]; then
        pair_speaker "$sp_name" "$sp_mac" "$rec_ctrl"
    elif [[ "$action" == *"Connect using"* ]]; then
        connect_only "$sp_mac" "$sp_name" "$rec_ctrl"
    else
        log "Unrecognized action for $sp_name ($sp_mac): $action. Skipping."
    fi
done

###########################################################################
# PulseAudio setup and loopback creation (unchanged)
###########################################################################
pulseaudio --start || log "Warning: PulseAudio failed to start."
if ! wait_for_pulseaudio; then
    log "Error: PulseAudio did not initialize properly."
fi

log "Loading virtual sink module..."
VIRTUAL_SINK=$(pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out)
log "Virtual sink created with index: $VIRTUAL_SINK"
sleep 2

for sp_mac in $(echo "$gameplan_json" | jq -r 'keys[]'); do
    connected_on=$(echo "$gameplan_json" | jq -r --arg sp "$sp_mac" '.[$sp].connected_on | join(",")')
    if [ -n "$connected_on" ]; then
        sink_name="bluez_sink.${sp_mac//:/_}.a2dp_sink"
        log "Loading loopback for sink: $sink_name"
        load_loopback "$sink_name"
    fi
done

log "Waking up all sinks..."
while IFS= read -r line; do
    sink_name=$(echo "$line" | awk '{print $2}')
    log "Unsuspending sink $sink_name..."
    pactl suspend-sink "$sink_name" 0
done < <(pactl list short sinks)

log "Unloading module-suspend-on-idle..."
for module in $(pactl list short modules | grep module-suspend-on-idle | awk '{print $1}'); do
    log "Unloading module-suspend-on-idle module $module"
    pactl unload-module "$module"
done

log "Connection flow complete."
