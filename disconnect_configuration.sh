#!/bin/bash
set -e

# Usage: ./disconnect_configuration.sh <configID> <configName> <speakersJson> <settingsJson>
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <configID> <configName> <speakersJson> <settingsJson>"
    exit 1
fi

CONFIG_ID="$1"
CONFIG_NAME="$2"
SPEAKERS_JSON="$3"
SETTINGS_JSON="$4"

echo "Starting disconnect process for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)..."

# Parse the speakers JSON into an associative array.
declare -A speakers
while IFS=, read -r mac name; do
    speakers["$mac"]="$name"
done < <(echo "$SPEAKERS_JSON" | jq -r 'to_entries[] | "\(.key),\(.value)"')

# Discover available Bluetooth controllers.
controllers=()
while IFS= read -r line; do
    if [[ $line =~ Controller[[:space:]]+([[:xdigit:]:]{17}) ]]; then
        controllers+=("${BASH_REMATCH[1]}")
    fi
done < <(bluetoothctl list)

if [ ${#controllers[@]} -eq 0 ]; then
    echo "No Bluetooth controllers found."
    exit 1
fi
echo "Found controllers: ${controllers[@]}"

# Loop through each controller to disconnect any speaker device that's connected.
for ctrl in "${controllers[@]}"; do
    echo "Checking connected devices on controller $ctrl..."
    # Select the controller.
    CONNECTED_OUTPUT=$(bluetoothctl <<EOF
select $ctrl
devices Connected
EOF
)
    # For each connected device, extract the MAC and if it exists in speakers, disconnect it.
    while IFS= read -r line; do
        if [[ $line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]] ]]; then
            dev_mac="${BASH_REMATCH[1]}"
            if [ -n "${speakers[$dev_mac]}" ]; then
                echo "Disconnecting speaker ${speakers[$dev_mac]} ($dev_mac) on controller $ctrl..."
                bluetoothctl <<EOF
select $ctrl
disconnect $dev_mac
EOF
                sleep 2
            fi
        fi
    done <<< "$CONNECTED_OUTPUT"
done

# Unload loopback modules for each speaker sink.
for mac in "${!speakers[@]}"; do
    sink_name="bluez_sink.${mac//:/_}.a2dp_sink"
    echo "Unloading loopback modules for sink: $sink_name..."
    module_ids=$(pactl list short modules | grep module-loopback | grep "$sink_name" | awk '{print $1}')
    if [ -n "$module_ids" ]; then
        for id in $module_ids; do
            echo "Unloading module $id..."
            pactl unload-module "$id" || echo "Module $id failed to unload."
        done
    fi
done

# Unload all virtual sink modules.
echo "Unloading virtual sink modules..."
for mod in $(pactl list short modules | grep module-null-sink | awk '{print $1}'); do
    echo "Unloading module $mod..."
    pactl unload-module "$mod" || echo "Module $mod could not be unloaded."
done

echo "Disconnect process complete for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)."
