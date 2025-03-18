#!/bin/bash
set -e

# Preconfigured speakers: keys are speaker names and values are their MAC addresses.
declare -A speakers=(
  ["Bose Color Soundlink"]="00:0C:8A:FF:18:FE"
  ["JBL Flip 4"]="98:52:3D:A3:C4:1B"
)

# Function to perform Bluetooth pairing for a speaker
pair_speaker() {
    local speaker_name=$1
    local mac_address=$2

    echo "Pairing with $speaker_name ($mac_address)..."
    # Run bluetoothctl in an interactive block
    bluetoothctl <<EOF
scan on
pair $mac_address
trust $mac_address
connect $mac_address
scan off
EOF
    echo "$speaker_name paired successfully."
}

echo "Starting Bluetooth pairing process for preconfigured speakers..."

# Loop through each preconfigured speaker
for speaker in "${!speakers[@]}"; do
    echo "---------------------------------------------"
    echo "Please turn on \"$speaker\" and put it in pairing mode."
    read -p "Press [Enter] once \"$speaker\" is ready: "
    
    pair_speaker "$speaker" "${speakers[$speaker]}"
done

echo "All speakers paired successfully."

# Allow a moment for the Bluetooth sinks to register
sleep 5

# Start PulseAudio if not already running
pulseaudio --start

# Create a virtual sink for combined output
echo "Loading virtual sink module..."
VIRTUAL_SINK=$(pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out)
echo "Virtual sink created with index: $VIRTUAL_SINK"

# Allow time for the virtual sink to register
sleep 2

# Set up loopback modules for each speaker.
# Assumes the sink names are in the format bluez_output.<MAC_with_underscores>.1
echo "Loading loopback modules for each speaker..."
for speaker in "${!speakers[@]}"; do
    mac="${speakers[$speaker]}"
    sink_name="bluez_output.${mac//:/_}.1"
    echo "Loading loopback for sink: $sink_name"
    LOOPBACK=$(pactl load-module module-loopback source=virtual_out.monitor sink="$sink_name" latency_msec=100)
    echo "Loopback module for $sink_name loaded with index: $LOOPBACK"
done

echo "Startup configuration complete."
