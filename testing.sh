#!/usr/bin/env bash
set -e

# This script queries all Bluetooth controllers and outputs a nested JSON.
# The output structure is:
# {
#    "controller_mac1": {
#         "paired": { "device_mac1": "Name", "device_mac2": "Name", ... },
#         "connected": { "device_mac1": "Name", ... }
#    },
#    "controller_mac2": { ... }
# }

# Get the list of controllers
controllers=$(bluetoothctl list)
if [ -z "$controllers" ]; then
  echo "{}"
  exit 0
fi

# Build an array of controller MAC addresses
declare -a ctrl_array=()
while IFS= read -r line; do
  if [[ $line =~ ^Controller[[:space:]]([[:xdigit:]:]{17}) ]]; then
    ctrl_array+=( "${BASH_REMATCH[1]}" )
  fi
done <<< "$controllers"

# Start JSON output
echo "{"
first_controller=1
for ctrl in "${ctrl_array[@]}"; do
    if [ $first_controller -eq 0 ]; then
         echo ","
    fi
    first_controller=0
    echo "  \"$ctrl\": {"

    # Query paired devices for this controller.
    paired=$(bluetoothctl <<EOF
select $ctrl
devices Paired
EOF
)
    # Build JSON string for paired devices.
    paired_json=""
    first_device=1
    while IFS= read -r dev_line; do
         if [[ $dev_line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]](.+) ]]; then
              dev_mac="${BASH_REMATCH[1]}"
              dev_name="${BASH_REMATCH[2]}"
              # Escape any quotes in the device name.
              dev_name=$(printf "%s" "$dev_name" | sed 's/"/\\"/g')
              if [ $first_device -eq 0 ]; then
                  paired_json+=", "
              fi
              first_device=0
              paired_json+="\"$dev_mac\": \"$dev_name\""
         fi
    done <<< "$paired"

    # Query connected devices for this controller.
    connected=$(bluetoothctl <<EOF
select $ctrl
devices Connected
EOF
)
    # Build JSON string for connected devices.
    connected_json=""
    first_device=1
    while IFS= read -r dev_line; do
         if [[ $dev_line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]](.+) ]]; then
              dev_mac="${BASH_REMATCH[1]}"
              dev_name="${BASH_REMATCH[2]}"
              dev_name=$(printf "%s" "$dev_name" | sed 's/"/\\"/g')
              if [ $first_device -eq 0 ]; then
                  connected_json+=", "
              fi
              first_device=0
              connected_json+="\"$dev_mac\": \"$dev_name\""
         fi
    done <<< "$connected"

    echo "    \"paired\": { $paired_json },"
    echo "    \"connected\": { $connected_json }"
    echo -n "  }"
done
echo
echo "}"
