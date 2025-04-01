#!/usr/bin/env bash
set -e

###########################################################################
# Logging helper (send logs to stderr so they don't mix with stdout)
###########################################################################
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

###########################################################################
# Function to wait for PulseAudio to start
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
# Function to load loopback module with retry logic
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
# Main Script Flow:
# 1. Generate gameplan JSON using gameplan.sh.
# 2. Apply the gameplan using apply_gameplan.py and capture its output.
# 3. Create loopbacks for connected Bluetooth sinks via PulseAudio.
# 4. Unsuspend all sinks and unload module-suspend-on-idle.
# 5. Finally, echo the final connection status JSON.
###########################################################################

# Usage: connect_configuration.sh <configID> <configName> <speakersJson> <settingsJson>
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <configID> <configName> <speakersJson> <settingsJson>" >&2
    exit 1
fi

CONFIG_ID="$1"
CONFIG_NAME="$2"
SPEAKERS_JSON="$3"
SETTINGS_JSON="$4"

echo "Starting connection process for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)..." >&2

# Generate gameplan JSON using gameplan.sh.
# We filter out any log lines before the first '{'
GAMEPLAN_FILE=$(mktemp /tmp/gameplan.XXXXXX.json)
echo "Generating game plan..." >&2
./gameplan.sh "$CONFIG_ID" "$CONFIG_NAME" "$SPEAKERS_JSON" "$SETTINGS_JSON" | sed -n '/^{/,$p' > "$GAMEPLAN_FILE"

echo "Game plan generated:" >&2
cat "$GAMEPLAN_FILE" >&2
echo "" >&2

# Apply the gameplan using the Python script and capture its output.
echo "Applying game plan..." >&2
RESULT=$(python3 apply_gameplan.py "$GAMEPLAN_FILE")
echo "$RESULT"

# Log the result to stderr for debugging.
echo "Result from apply_gameplan.py:" >&2
echo "$RESULT" >&2

###########################################################################
# Create loopbacks for connected speakers by checking PulseAudio sinks.
###########################################################################
log "Creating loopbacks for connected Bluetooth sinks..."

# Ensure PulseAudio is running.
pulseaudio --start || log "Warning: PulseAudio failed to start."
if ! wait_for_pulseaudio; then
    log "Error: PulseAudio did not initialize properly."
    exit 1
fi

# Load a virtual sink module.
log "Loading virtual sink module..."
VIRTUAL_SINK=$(pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out)
log "Virtual sink created with index: $VIRTUAL_SINK"
sleep 2

# List all sinks; for each sink that matches a Bluetooth sink pattern, load loopback.
SINKS=$(pactl list short sinks | awk '{print $2}')
for sink in $SINKS; do
    if [[ "$sink" == bluez_sink.*.a2dp_sink* ]]; then
        log "Found Bluetooth sink: $sink. Loading loopback..."
        load_loopback "$sink"
    else
        log "Skipping sink: $sink"
    fi
done

###########################################################################
# Unsuspend all sinks.
###########################################################################
log "Waking up all sinks..."
while IFS= read -r line; do
    sink_name=$(echo "$line" | awk '{print $2}')
    log "Unsuspending sink $sink_name..."
    pactl suspend-sink "$sink_name" 0
done < <(pactl list short sinks)

###########################################################################
# Unload module-suspend-on-idle to prevent auto-suspension.
###########################################################################
log "Unloading module-suspend-on-idle..."
for module in $(pactl list short modules | grep module-suspend-on-idle | awk '{print $1}'); do
    log "Unloading module-suspend-on-idle module $module"
    pactl unload-module "$module"
done

# Clean up temporary gameplan file.
rm "$GAMEPLAN_FILE"

echo "Connection process complete." >&2
# Echo the final connection status JSON as the only stdout output.
echo "$RESULT"
