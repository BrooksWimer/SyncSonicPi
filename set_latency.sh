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

# Find and unload all loopback modules that match this sink.
module_ids=$(pactl list short modules | grep module-loopback | grep "$sink_name" | awk '{print $1}')
if [ -n "$module_ids" ]; then
  echo "Unloading existing loopback modules for sink $sink_name..."
  for id in $module_ids; do
    echo "Unloading module $id..."
    pactl unload-module "$id" || echo "Module $id not loaded or failed to unload."
  done
fi

echo "Loading new loopback for sink $sink_name with latency ${latency} ms..."
module_index=$(pactl load-module module-loopback source=virtual_out.monitor sink="$sink_name" latency_msec="$latency")
echo "New loopback module loaded with index: $module_index"
