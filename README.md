# 📦 SyncSonic Pi Server

This repository contains the Raspberry Pi backend that powers the SyncSonic mobile app. It connects to Bluetooth speakers and phones, manages audio routing, and provides a REST API for the mobile UI to interact with.

## 🚀 Features

- 🔊 Connects and configures Bluetooth speakers using BlueZ and PipeWire
- 📱 Pairs with a phone to receive A2DP audio input
- 🔄 Manages latency, volume, and stereo balance per speaker
- 🔌 Automatically resets or reconnects adapters as needed
- 🌐 REST API served by Flask with modular endpoint structure

## 🧰 Requirements

- Raspberry Pi (tested on Pi Zero W and others)
- Python 3.9+
- `bluez`,`libspa-0.2-bluetooth`, `flask`, `dbus-python`
- `wpctl`, `bluetoothctl`, `pactl`

Install Python dependencies:
```bash
pip install flask dbus-python
```

## 📁 Folder Structure

```
SyncSonicPiRepo/
├── api_server.py                  # Main Flask server
├── auto_connect.sh                # Auto-connect utility script
├── reset_bt_adapters.sh          # Resets BT modules when needed
├── endpoints/                    # Modular Flask API endpoints
│   ├── connect_phone.py
│   ├── connect_one_speaker.py
│   ├── disconnect.py
│   ├── latency.py
│   ├── paired_devices.py
│   ├── scan.py
│   └── setup_box.py
└── utils/                         # Utility functions (e.g., state mgmt, audio control)
```

## 🔌 Usage

1. **Run the API server:**
```bash
python3 api_server.py
```

The server will start and expose REST endpoints for:

- `/connect-phone`
- `/connect-one`
- `/disconnect`
- `/set-latency`
- `/reset-bluetooth`
- And more

2. **Trigger scripts when needed:**
```bash
./reset_bt_adapters.sh
./auto_connect.sh
```

## 🔧 Configuration

You may need to edit:

- `reset_bt_adapters.sh` for your hardware
- Bluetooth controller MAC addresses in the global state manager
- Audio backend assumptions (e.g., profile is `a2dp-sink`, sink name is `virtual_out`)

## 📡 API Integration

This Pi server is designed to work with the [SyncSonic mobile app](https://github.com/BrooksWimer/Sync-Sonic-App) and exposes endpoints consumed directly by the app.

## ✅ Status

- [x] Multi-speaker support
- [x] Reliable phone pairing
- [x] Low-latency loopbacks
- [x] Bluetooth error handling
- [ ] Full persistent config system (coming soon)
