#!/bin/bash
set -e

EXPECTED_ADAPTER_COUNT=4   # Include all expected hciX, including hci0 if desired
HUB_PATH="1-1"             # Your USB hub's device path

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

get_mac() {
  hciconfig "$1" | grep 'BD Address' | awk '{print $3}'
}

detect_adapters() {
  hciconfig | grep -o '^hci[0-9]*'
}

get_usb_device_for_hci() {
  local hci="$1"
  local path
  path=$(readlink -f /sys/class/bluetooth/"$hci"/device)

  while [[ -n "$path" && ! $(basename "$path") =~ ^[0-9]-[0-9](\.[0-9]+)*$ ]]; do
    path=$(dirname "$path")
  done

  echo "$(basename "$path")"
}


reset_usb_device() {
  local dev_name="$1"
  log "Unbinding USB device $dev_name..."
  echo "$dev_name" | sudo tee /sys/bus/usb/drivers/usb/unbind > /dev/null
  sleep 1
  log "Rebinding USB device $dev_name..."
  echo "$dev_name" | sudo tee /sys/bus/usb/drivers/usb/bind > /dev/null
  sleep 5
}

power_cycle_entire_hub() {
  log "🔌 Power cycling USB hub $HUB_PATH..."
  echo "$HUB_PATH" | sudo tee /sys/bus/usb/drivers/usb/unbind
  sleep 3
  echo "$HUB_PATH" | sudo tee /sys/bus/usb/drivers/usb/bind
  log "✅ Hub power cycle complete."
  sleep 8
}

all_adapters_healthy() {
  local bad=false
  local hci_list
  hci_list=($(detect_adapters))

  if (( ${#hci_list[@]} < EXPECTED_ADAPTER_COUNT )); then
    log "❌ Missing adapters! Expected $EXPECTED_ADAPTER_COUNT, found ${#hci_list[@]}"
    return 1
  fi

  for hci in "${hci_list[@]}"; do
    mac=$(get_mac "$hci")
    if [[ "$mac" == "00:00:00:00:00:00" || -z "$mac" ]]; then
      log "❌ $hci has invalid MAC: $mac"
      bad=true
    else
      log "✅ $hci has valid MAC: $mac"
    fi
  done

  $bad && return 1 || return 0
}


ensure_all_adapters_up() {
  for hci in $(detect_adapters); do
    for i in {1..5}; do
      if sudo hciconfig "$hci" up 2>/dev/null; then
        log "✅ $hci successfully brought UP."
        break
      else
        log "⚠️ Failed to bring $hci up. Retry $i..."
        sleep 2
      fi
    done
  done
}

### 🔁 Main Loop
log "Starting Bluetooth adapter recovery..."
log "🔄 ResettingPulseAudio and bluetoothd..."



log "✅ Audio and Bluetooth services restarted."

while true; do
  missing_adapters=false
  invalid_adapters=()

  hci_list=($(detect_adapters))

  if (( ${#hci_list[@]} < EXPECTED_ADAPTER_COUNT )); then
    log "❌ Missing adapters! Expected $EXPECTED_ADAPTER_COUNT, found ${#hci_list[@]}"
    missing_adapters=true
  fi

  for hci in "${hci_list[@]}"; do
    mac=$(get_mac "$hci")
    if [[ "$mac" == "00:00:00:00:00:00" || -z "$mac" ]]; then
      log "❌ $hci has invalid MAC: $mac"
      invalid_adapters+=("$hci")
    else
      log "✅ $hci has valid MAC: $mac"
    fi
  done

  # If adapters are missing, power cycle the whole hub
  if $missing_adapters; then
    log "⚠️ Some adapters disappeared. Performing hub power cycle..."
    power_cycle_entire_hub
    sleep 8
    continue
  fi

  # Retry resets for any invalid adapters
  if (( ${#invalid_adapters[@]} > 0 )); then
    log "🔁 Retrying USB reset for adapters with invalid MACs..."
    for hci in "${invalid_adapters[@]}"; do
      dev_name=$(get_usb_device_for_hci "$hci")
      if [[ -n "$dev_name" ]]; then
        reset_usb_device "$dev_name"
      else
        log "⚠️ Could not find USB device for $hci"
      fi
    done
    sleep 3
    continue
  fi


  # Ensure all adapters are turned on
  log "🔌 Ensuring all adapters are turned ON..."
  ensure_all_adapters_up


  log "🎉 All Bluetooth adapters are present and healthy."

 
  break
done
