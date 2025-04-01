#!/usr/bin/env bash
set -e

###############################################################################
# Logging helper
###############################################################################
log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

###############################################################################
# Validate arguments and parse JSON input
###############################################################################
if [ "$#" -ne 4 ]; then
  log "Usage: $0 <configID> <configName> <speakersJson> <settingsJson>"
  exit 1
fi

CONFIG_ID="$1"
CONFIG_NAME="$2"
SPEAKERS_JSON="$3"
SETTINGS_JSON="$4"

log "Starting gameplan generation for configuration '$CONFIG_NAME' (ID: $CONFIG_ID)..."

# Parse speakers: mapping MAC -> name
declare -A speakers
while IFS=, read -r mac name; do
  speakers["$mac"]="$name"
done < <(echo "$SPEAKERS_JSON" | jq -r 'to_entries[] | "\(.key),\(.value)"')

# Parse settings (not used in game plan yet)
declare -A volumes
declare -A latencies
while IFS=, read -r mac volume latency; do
  volumes["$mac"]="$volume"
  latencies["$mac"]="$latency"
done < <(echo "$SETTINGS_JSON" | jq -r 'to_entries[] | "\(.key),\(.value.volume),\(.value.latency)"')

###############################################################################
# Build nested dictionaries for each controller (port)
# nested_paired["<ctrl>:<dev_mac>"] = <device name>
# nested_connected["<ctrl>:<dev_mac>"] = <device name>
###############################################################################
declare -A nested_paired
declare -A nested_connected
declare -a ctrl_array

all_controllers="$(bluetoothctl list)"
if [ -z "$all_controllers" ]; then
  log "No controllers found."
  exit 1
fi

while IFS= read -r line; do
  if [[ $line =~ ^Controller[[:space:]]([[:xdigit:]:]{17}) ]]; then
    ctrl="${BASH_REMATCH[1]}"
    ctrl_array+=( "$ctrl" )
  fi
done <<< "$all_controllers"

###############################################################################
# For each controller, query paired and connected devices.
###############################################################################
for ctrl in "${ctrl_array[@]}"; do
  paired=$(bluetoothctl <<EOF
select $ctrl
devices Paired
EOF
)
  while IFS= read -r dev_line; do
    if [[ $dev_line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]](.+) ]]; then
      dev_mac="${BASH_REMATCH[1]}"
      dev_name="${BASH_REMATCH[2]}"
      nested_paired["$ctrl:$dev_mac"]="$dev_name"
    fi
  done <<< "$paired"

  connected=$(bluetoothctl <<EOF
select $ctrl
devices Connected
EOF
)
  while IFS= read -r dev_line; do
    if [[ $dev_line =~ ^Device[[:space:]]([[:xdigit:]:]{17})[[:space:]](.+) ]]; then
      dev_mac="${BASH_REMATCH[1]}"
      dev_name="${BASH_REMATCH[2]}"
      nested_connected["$ctrl:$dev_mac"]="$dev_name"
    fi
  done <<< "$connected"
done

###############################################################################
# Build the game plan based on target speakers and current state.
# For each speaker determine:
#   - paired_list: controllers where it's paired
#   - connected_list: controllers where it's connected
#   - rec_ctrl: recommended controller (free and available)
#   - disconnect_list: any controllers in connected_list that are NOT rec_ctrl
###############################################################################
declare -A gameplan  # Key: speaker MAC -> JSON object string
declare -A assignedControllers  # Tracks which controllers are already assigned

for sp_mac in "${!speakers[@]}"; do
  sp_name="${speakers[$sp_mac]}"
  paired_list=()
  connected_list=()

  # Check every controller for pairing/connection of this speaker.
  for ctrl in "${ctrl_array[@]}"; do
    key="$ctrl:$sp_mac"
    if [ -n "${nested_paired[$key]}" ]; then
      paired_list+=( "$ctrl" )
    fi
    if [ -n "${nested_connected[$key]}" ]; then
      connected_list+=( "$ctrl" )
    fi
  done

  # Filter out controllers already assigned.
  free_paired_list=()
  for ctrl in "${paired_list[@]}"; do
    if [ -z "${assignedControllers[$ctrl]}" ]; then
      free_paired_list+=( "$ctrl" )
    fi
  done

  free_connected_list=()
  for ctrl in "${connected_list[@]}"; do
    if [ -z "${assignedControllers[$ctrl]}" ]; then
      free_connected_list+=( "$ctrl" )
    fi
  done

  # Determine recommended controller (rec_ctrl) and action.
  if [ ${#free_connected_list[@]} -gt 0 ]; then
    rec_ctrl="${free_connected_list[0]}"
    action="No action: Already connected on $rec_ctrl."
    assignedControllers["$rec_ctrl"]="$sp_mac"
  elif [ ${#free_paired_list[@]} -gt 0 ]; then
    rec_ctrl="${free_paired_list[0]}"
    action="Action: Connect using controller $rec_ctrl (speaker is paired on $(IFS=,; echo "${paired_list[*]}"))."
    assignedControllers["$rec_ctrl"]="$sp_mac"
  else
    rec_ctrl=""
    for ctrl in "${ctrl_array[@]}"; do
      if [ -z "${assignedControllers[$ctrl]}" ]; then
        rec_ctrl="$ctrl"
        break
      fi
    done
    if [ -n "$rec_ctrl" ]; then
      action="Action: Pair and connect using controller $rec_ctrl (speaker not paired anywhere)."
      assignedControllers["$rec_ctrl"]="$sp_mac"
    else
      action="Error: No free controller available for connection."
    fi
  fi

  # Compute disconnect list: controllers in connected_list that are not rec_ctrl.
  disconnect_list=()
  for ctrl in "${connected_list[@]}"; do
    if [ "$ctrl" != "$rec_ctrl" ]; then
      disconnect_list+=( "$ctrl" )
    fi
  done

  # Build JSON arrays for paired, connected, and disconnect lists.
  paired_json="["
  for i in "${!paired_list[@]}"; do
    if [ $i -gt 0 ]; then
      paired_json+=", "
    fi
    paired_json+="\"${paired_list[$i]}\""
  done
  paired_json+="]"

  connected_json="["
  for i in "${!connected_list[@]}"; do
    if [ $i -gt 0 ]; then
      connected_json+=", "
    fi
    connected_json+="\"${connected_list[$i]}\""
  done
  connected_json+="]"

  disconnect_json="["
  for i in "${!disconnect_list[@]}"; do
    if [ $i -gt 0 ]; then
      disconnect_json+=", "
    fi
    disconnect_json+="\"${disconnect_list[$i]}\""
  done
  disconnect_json+="]"

  esc_name=$(printf "%s" "$sp_name" | sed 's/"/\\"/g')
  esc_action=$(printf "%s" "$action" | sed 's/"/\\"/g')

  gameplan["$sp_mac"]="{\"name\": \"${esc_name}\", \"paired_on\": ${paired_json}, \"connected_on\": ${connected_json}, \"disconnect\": ${disconnect_json}, \"action\": \"${esc_action}\"}"
done

###############################################################################
# Output the final game plan as JSON.
###############################################################################
echo "{"
first=1
for key in "${!gameplan[@]}"; do
  if [ $first -eq 1 ]; then
    first=0
  else
    echo ","
  fi
  echo "  \"$key\": ${gameplan[$key]}"
done
echo
echo "}"
