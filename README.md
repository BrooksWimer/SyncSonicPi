# Raspberry Pi Bluetooth Audio Receiver with Spotify Connect

This guide provides step-by-step instructions to set up a **Raspberry Pi** as a **Bluetooth audio receiver** and **Spotify Connect device** using **BlueALSA** and **Raspotify**.

## Features
- Stream audio from **Bluetooth devices** to the Raspberry Pi.
- Act as a **Spotify Connect device** for playback via **Raspotify**.
- Use **BlueALSA** to route Bluetooth audio to ALSA.

---

## 1. Prerequisites
### Hardware
- Raspberry Pi (any model, preferably Pi 3 or newer)
- Bluetooth USB adapter (if not built-in)
- Bluetooth speaker or audio output device
- MicroSD card (minimum 8GB)

### Software
- Raspberry Pi OS (Lite) **Debian 12 "Bookworm"**

---

## 2. Install Raspberry Pi OS
1. Download **Raspberry Pi Imager** from [here](https://www.raspberrypi.org/software/).
2. Insert your **microSD card** and open the Raspberry Pi Imager.
3. Select **Raspberry Pi OS (Lite) (Debian 12 "Bookworm")**.
4. Click "Flash" and wait for the process to complete.
5. Insert the microSD card into your Raspberry Pi and boot it up.

### Enable SSH and Wi-Fi (Optional)
If you need SSH access, create an **empty file** named `ssh` in the boot partition.
For Wi-Fi, create a `wpa_supplicant.conf` file:
```bash
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
network={
    ssid="YourWiFiSSID"
    psk="YourWiFiPassword"
}
```

---

## 3. Install Dependencies

### Update the system:
```bash
sudo apt update
sudo apt upgrade -y
```

### Install BlueALSA (Bluetooth Audio Support):
```bash
sudo apt install bluealsa bluez-utils
```

### Install Raspotify (Spotify Connect Client):
```bash
curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
```

### Install ALSA utilities:
```bash
sudo apt install alsa-utils
```

---

## 4. Bluetooth Configuration

### Install Bluetooth utilities:
```bash
sudo apt install pi-bluetooth
```

### Check if Bluetooth service is running:
```bash
sudo systemctl status bluetooth
```

### Pair and Connect the Bluetooth Speaker:
```bash
bluetoothctl
power on
agent on
default-agent
scan on
pair 00:0C:8A:FF:18:FE  # Replace with your speaker's MAC address
trust 00:0C:8A:FF:18:FE
connect 00:0C:8A:FF:18:FE
exit
```

### Verify the Connection:
```bash
bluetoothctl info 00:0C:8A:FF:18:FE
```

---

## 5. BlueALSA Setup

### Restart BlueALSA service:
```bash
sudo systemctl restart bluealsa
```

### Check if BlueALSA is handling audio:
```bash
bluealsa-aplay -L
```

---

## 6. Raspotify Setup (Spotify Connect)

### Configure Spotify Credentials:
1. Visit the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/applications).
2. **Create an App** and obtain your **Client ID** and **Client Secret**.

### Edit Raspotify Configuration:
```bash
sudo nano /etc/default/raspotify
```
Add the following:
```bash
SPOTIFY_CLIENT_ID="your_client_id"
SPOTIFY_CLIENT_SECRET="your_client_secret"
```

### Restart Raspotify:
```bash
sudo systemctl restart raspotify
```

---

## 7. Testing Audio

### Test audio output using ALSA:
```bash
aplay -D bluealsa /usr/share/sounds/alsa/Front_Center.wav
```

### Test Spotify Playback:
1. Open the **Spotify app** on your phone/computer.
2. Select **your Raspberry Pi** as the playback device.
3. Play a song and verify audio output.

---

## 8. Troubleshooting

### No Sound?
- Ensure **PulseAudio is not interfering**:
  ```bash
  sudo systemctl --user stop pulseaudio
  ```
- Reboot and reconnect the Bluetooth speaker.

### Bluetooth Issues?
- Restart the Bluetooth service:
  ```bash
  sudo systemctl restart bluetooth
  ```
- Try reconnecting the speaker:
  ```bash
  bluetoothctl connect 00:0C:8A:FF:18:FE
  ```

### Raspotify Issues?
- Check logs for errors:
  ```bash
  journalctl -u raspotify --no-pager --lines=100
  ```
- Restart Raspotify:
  ```bash
  sudo systemctl restart raspotify
  ```

