#!/usr/bin/env bash
set -euo pipefail

EXPECTED_ADAPTER_COUNT="${1:-4}"  # how many HCIs you expect
HUB_PATH="1-1"                    # your USB hub’s device path
ENVFILE=/etc/default/syncsonic     # where we’ll record the reserved HCI

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

get_mac() {
  hciconfig "$1" | awk '/BD Address/ { print $3 }'
}

detect_adapters() {
  hciconfig | grep -o '^hci[0-9]*'
}

get_usb_device_for_hci() {
  local hci="$1" path
  path=$(readlink -f /sys/class/bluetooth/"$hci"/device)
  while [[ -n "$path" && ! $(basename "$path") =~ ^[0-9]-[0-9](\.[0-9]+)*$ ]]; do
    path=$(dirname "$path")
  done
  basename "$path"
}

reset_usb_device() {
  local dev="$1"
  log "Unbinding USB device $dev…"
  echo "$dev" | sudo tee /sys/bus/usb/drivers/usb/unbind >/dev/null
  sleep 1
  log "Rebinding USB device $dev…"
  echo "$dev" | sudo tee /sys/bus/usb/drivers/usb/bind >/dev/null
  sleep 5
}

power_cycle_entire_hub() {
  log "🔌 Power-cycling USB hub $HUB_PATH…"
  echo "$HUB_PATH" | sudo tee /sys/bus/usb/drivers/usb/unbind
  sleep 3
  echo "$HUB_PATH" | sudo tee /sys/bus/usb/drivers/usb/bind
  log "✅ Hub cycle done."
  sleep 8
}

all_adapters_healthy() {
  local bad=false hci_list mac
  IFS=$'\n' read -r -d '' -a hci_list < <(detect_adapters && printf '\0')
  (( ${#hci_list[@]} < EXPECTED_ADAPTER_COUNT )) && return 1
  for hci in "${hci_list[@]}"; do
    mac=$(get_mac "$hci")
    if [[ -z "$mac" || "$mac" == "00:00:00:00:00:00" ]]; then
      bad=true
      break
    fi
  done
  $bad && return 1 || return 0
}

ensure_all_adapters_up() {
  for hci in $(detect_adapters); do
    for i in {1..5}; do
      if sudo hciconfig "$hci" up 2>/dev/null; then
        log "✅ $hci is UP."
        break
      else
        log "⚠️ $hci up failed, retry $i."
        sleep 2
      fi
    done
  done
}

### 🔁 Main loop

# log "🚀 Quick precheck…"
# all_adapters_healthy && { log "🎯 All good. Exiting."; exit 0; }
# log "⚡ Issues found. Running full reset…"

while true; do
  missing=false
  invalid=()
  hci_list=($(detect_adapters))

  (( ${#hci_list[@]} < EXPECTED_ADAPTER_COUNT )) && missing=true

  for hci in "${hci_list[@]}"; do
    mac=$(get_mac "$hci")
    [[ -z "$mac" || "$mac" == "00:00:00:00:00:00" ]] && invalid+=("$hci")
  done

  if $missing; then
    log "⚠️ Missing adapters. Hub cycle."
    power_cycle_entire_hub
    continue
  fi

  if (( ${#invalid[@]} )); then
    log "🔁 Resetting invalid adapters: ${invalid[*]}"
    for hci in "${invalid[@]}"; do
      dev=$(get_usb_device_for_hci "$hci")
      [[ -n "$dev" ]] && reset_usb_device "$dev"
    done
    continue
  fi

  log "🔌 Bringing all adapters UP…"
  ensure_all_adapters_up
  log "🎉 All adapters healthy."
  break
done

### ✨ New: detect & name adapters, record UART one

declare -a ALL_HCIS
mapfile -t ALL_HCIS < <(detect_adapters)

RESERVED=""
count=1

for hci in "${ALL_HCIS[@]}"; do
  # pull “Bus: <TYPE>” line
  bus_type=$(sudo hciconfig "$hci" | awk '/Bus:/ {print $5; exit}')
  if [[ "$bus_type" == "UART" ]]; then
    RESERVED="$hci"
    sudo hciconfig "$hci" name "Sync-Sonic"
    log "📡 Reserved $hci for phone (UART bus)."
  else
    sudo hciconfig "$hci" name "raspberrypi-$count"
    log "🔊 Named $hci → raspberrypi-$count"
    count=$((count+1))
  fi
done

# Persist for systemd + Python
if [[ -n "$RESERVED" ]]; then
  echo "export RESERVED_HCI=$RESERVED" | sudo tee /etc/default/syncsonic >/dev/null
  log "💾 exported RESERVED_HCI=$RESERVED to $ENVFILE"
else
  log "⚠️ No UART adapter found; RESERVED_HCI left unset."
fi
