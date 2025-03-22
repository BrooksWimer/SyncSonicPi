#!/bin/bash
set -e

# Usage: ./set_latency.sh <mac> <latency>
if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <mac> <latency>"
  exit 1
fi

mac="$1"
latency="$2"
# Compute the sink name by replacing colons with underscores.
sink_name="bluez_sink.${mac//:/_}.a2dp_sink"

# Find any loopback module that has been loaded for this sink.
module_id=$(pactl list short modules | grep module-loopback | grep "$sink_name" | awk '{print $1}')

if [ -n "$module_id" ]; then
  echo "Unloading existing loopback module $module_id for sink $sink_name..."
  pactl unload-module "$module_id"
fi

echo "Loading new loopback for sink $sink_name with latency ${latency} ms..."
module_index=$(pactl load-module module-loopback source=virtual_out.monitor sink="$sink_name" latency_msec="$latency")
echo "New loopback module loaded with index: $module_index"
