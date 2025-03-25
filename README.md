# SyncSonicPi

A Raspberry Pi-based multi-speaker audio synchronization system that works in conjunction with the SyncSonic mobile app to create a synchronized multi-room audio experience.

## Overview

SyncSonicPi is the backend component of the SyncSonic system, running on a Raspberry Pi. It manages multiple Bluetooth speakers through multiple Bluetooth adapters, handling speaker discovery, pairing, connection, and audio synchronization. The system uses PulseAudio for advanced audio routing and provides a REST API for the SyncSonic mobile app to control the system.

## Hardware Requirements

- Raspberry Pi 4B
- 2x USB Bluetooth 5.0 adapters (in addition to the Pi's built-in Bluetooth)
- Supported Bluetooth speakers
- Stable network connection

## System Requirements

- Raspberry Pi OS (Latest version)
- Python 3
- Flask
- PulseAudio
- Bluetooth tools
- jq (JSON processor)

## Installation

1. **Update System and Install Dependencies**
```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y pulseaudio pulseaudio-module-bluetooth bluetooth bluez python3 python3-pip jq
curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
```

2. **Enable and Configure Bluetooth**
```bash
sudo systemctl enable bluetooth 
sudo systemctl start bluetooth

# Verify Bluetooth status
sudo systemctl status bluetooth

# If Bluetooth is blocked
rfkill list
sudo rfkill unblock bluetooth
```

3. **Configure Bluetooth Adapters**
```bash
# Enable USB Bluetooth adapters and disable built-in Bluetooth
sudo hciconfig hci0 up  # First USB adapter
sudo hciconfig hci1 up  # Second USB adapter
sudo hciconfig hci2 down  # Built-in Bluetooth (may vary)
```

4. **Install Python Dependencies**
```bash
pip3 install flask
```

5. **Clone Repository and Set Up**
```bash
git clone [your-repository-url]
cd SyncSonicPi
chmod +x *.sh  # Make shell scripts executable
```

## Configuration

1. **PulseAudio Setup**
```bash
# Start PulseAudio
pulseaudio --start

# Create virtual sink
pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out

# Set virtual sink as default
pactl set-default-sink virtual_out
```

2. **API Server Configuration**
- Edit `api_server.py` to set the correct host and port if needed
- Default port is 3000

## Usage

1. **Start the API Server**
```bash
python3 api_server.py
```

2. **API Endpoints**
- `/scan` - GET: Scan for available Bluetooth speakers
- `/pair` - POST: Pair selected speakers
- `/connect` - POST: Connect a speaker configuration
- `/disconnect` - POST: Disconnect a speaker configuration
- `/volume` - POST: Adjust speaker volume
- `/latency` - POST: Adjust speaker latency

## Integration with SyncSonic Mobile App

The SyncSonic mobile app communicates with this Pi server through REST API calls. The app allows users to:
- Discover and select Bluetooth speakers
- Create and manage speaker configurations
- Control volume and latency settings
- Connect/disconnect speaker configurations

## Troubleshooting

1. **Bluetooth Issues**
```bash
# Check Bluetooth status
hciconfig -a
sudo systemctl status bluetooth

# If Bluetooth is not responding
sudo systemctl restart bluetooth
```

2. **Audio Issues**
```bash
# Check PulseAudio sinks
pactl list sinks short

# Restart PulseAudio
pulseaudio -k
pulseaudio --start
```

3. **Common Issues**
- If speakers won't connect, ensure they're in pairing mode
- If audio is out of sync, adjust latency settings
- If no sound, check PulseAudio sink configuration

## Scripts

- `api_server.py`: Main API server
- `connect_configuration.sh`: Handles speaker connection and audio routing
- `disconnect_configuration.sh`: Handles speaker disconnection
- `set_latency.sh`: Manages audio synchronization
- Additional utility scripts for setup and management

