sudo raspi-config
hostname -I
sudo apt-get update && sudo apt-get upgrade -y
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
sudo systemctl status bluetooth
pulseaudio --kill || true
pulseaudio --start
hciconfig -a
sudo hciconfig hci0 up
rfkill list
sudo rfkill unblock bluetooth
rfkill list
sudo hciconfig hci0 up
sudo hciconfig hci1 up
sudo hciconfig hci2 up
hciconfig -a
sudo hciconfig hci2 down
hciconfig -a
bluetoothctl
ls ~/.config/pipewire/
/etc/pipewire/
ls /usr/share/pipewire/pipewire.conf
/usr/share/pipewire/pipewire.conf
cat /usr/share/pipewire/pipewire.conf
ls ~/.config/pipewire/
pw-cli list-objects Node
systemctl --user status wireplumber
mkdir -p ~/.config/pipewire/
cp /usr/share/pipewire/pipewire.conf ~/.config/pipewire/
nano ~/.config/pipewire/pipewire.conf
cat ~/.config/pipewire/pipewire.conf
nano ~/.config/pipewire/pipewire.conf
mv ~/.config/pipewire/pipewire.conf ~/.config/pipewire/pipewire.conf.backup
nano ~/.config/pipewire/pipewire.conf
systemctl --user restart pipewire pipewire-pulse
bluetoothclt
bluetootchctl
bluetoothctl
hciconfig -a
pactl list sinks short
systemctl --user status pipewire
systemctl --user restart pipewire pipewire-pulse
systemctl --user status pipewire
bluetoothctl
bluetoothctl info 00:0C:8A:FF:18:FE
bluetoothctl
pactl list sinks short
systemctl --user status pipewire
pactl list sinks short
hciconfig -a
nano ~/.config/pipewire/pipewire.conf
systemctl --user restart pipewire pipewire-pulse
systemctl --user status pipewire
pactl list sinks shortbluetoothctl connect 00:0C:8A:FF:18:FE
pactl list sinks short
systemctl --user status pipewire
pactl list sinks short
cat ~/.config/pipewire/pipewire.conf
nano ~/.config/pipewire/pipewire.conf
systemctl --user restart pipewire pipewire-pulse
systemctl --user status pipewire
ls /usr/lib/pipewire-*/ | grep spa
find /usr -type d -name "pipewire*" 2>/dev/null
ls /usr/lib/aarch64-linux-gnu/pipewire-0.3/ | grep spa
sudo apt update
sudo apt install --reinstall libspa-0.2-modules -y
systemctl --user status pipewire-pulse
pactl list sinks short
pw-cli list-objects Node | grep -E 'id|bluez|alsa'
pactl list sinks
pactl load-module module-bluez5-discover
pactl list sinks
bluetoothctl
bluetoothctl paired-devices
bluetoothctl info
bluetoothctl devices Connected
pactl list sinks | grep -E 'Name|Description|State'
hciconfig
bluetoothctl info 98_52_3D_A3_C4_1B.1
pactl list short modules
pactl list sinks | grep -E 'Name|Module'
pactl unload-module 4294967295
pactl unload-module bluez_output.98_52_3D_A3_C4_1B.1
bluetoothctl
pactl load-module module-combine-sink sink_name=combined_out slaves=bluez_output.00_0C_8A_FF_18_FE.1,bluez_output.98_52_3D_A3_C4_1B.1
pactl set-default-sink combined_out
paplay /usr/share/sounds/alsa/Front_Center.wav
sudo systemctl restart bluetooth && systemctl --user restart pipewire wireplumber
qpwgraph
sudo apt install qpwgraph
qpwgraph
rfkill list
pactl list sinks short
wpctl status
pw-dump | less
pactl list cards
bluetoothctl disconnect 00:0C:8A:FF:18:FE
bluetoothctl disconnect 98:52:3D:A3:C4:1B
bluetoothctl info
cat /usr/share/wireplumber/bluetooth.lua
cat  /usr/share/pipewire/pipewire.conf.d/
cat /etc/pipewire/
cat ~/.config/pipewire
cat ~/.config/wireplumber
ls /usr/share/wireplumber/
cat /usr/share/wireplumber/bluetooth.conf
cat /usr/share/wireplumber/bluetooth.lua.d
cls /usr/share/wireplumber/bluetooth.lua.d
ls /usr/share/wireplumber/bluetooth.lua.d
ls /usr/share/wireplumber/bluetooth.lua.d/30-bluez-monitor.lua
cat /usr/share/wireplumber/bluetooth.lua.d/30-bluez-monitor.lua
cat /usr/share/wireplumber/bluetooth.lua.d/50-bluez-config.lua
cat /usr/share/wireplumber/bluetooth.lua.d/90-enable-all.lua
pactl load-module module-null-sink sink_name=virtual_out
pactl load-module module-loopback source=virtual_out.monitor
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_output.00_0C_8A_FF_18_FE.1 latency_msec=20
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_output.98_52_3D_A3_C4_1B.1 latency_msec=30
pactl set-default-sink virtual_out
pactl list sinks
pactl list sink-inputs
pactl set-default-sink virtual_out
pactl list sink-inputs
pw-dump
journalctl --user -xe | grep -i pipewire
export PIPEWIRE_DEBUG=2
journalctl --user -xe | grep -i pipewire
pactl list short modules | grep loopback
pactl unload-module 536870919
pactl list short modules | grep loopback
pactl unload-module 536870918
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_output.00_0C_8A_FF_18_FE.1 latency_msec=1000
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_output.98_52_3D_A3_C4_1B.1 latency_msec=1000
pactl list short modules | grep loopback
journalctl --user -xe | grep -i pipewire
systemctl --user stop pipewire pipewire-pulse wireplumber
pactl list sinks short
systemctl --user mask pipewire.service pipewire.socket pipewire-pulse.service pipewire-pulse.socket wireplumber.service
pactl list sinks short
sudo apt-get update && sudo apt-get install -y pulseaudio pulseaudio-module-bluetooth bluetooth bluez
pulseaudio --start
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
hciconfig -a
hci0 down
sudo hciconfig hci0 down
pactl list sinks short
pactl set-default-sink virtual_out
pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out
pactl set-default-sink virtual_out
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_output.00_0C_8A_FF_18_FE.1 latency_msec=100
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_output.98_52_3D_A3_C4_1B.1 latency_msec=100
paplay /usr/share/sounds/alsa/Front_Center.wav
pactl list sink-inputs
ps aux | grep pipewire
dpkg -l | grep pipewire
sudo apt-get purge -y pipewire wireplumber
pactl list sink-inputs
pactl list sinks short
sudo reboot
bluetoothctl
pactl list sinks short
hostname -I
nano ~/startup.sh
chmod +x ~/startup.sh
sudo nano /etc/systemd/system/syncsonic-startup.service
ls /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable syncsonic-startup.service
sudo reboot
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    bluetoothctl
hciconfig -a
bluetoothctl list
bluetoothctl
pactl load-module module-null-sink sink_name=virtual_out sink_properties=device.description=virtual_out
pactl set-default-sink virtual_out
pactl list sinks short
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_sink.00_0C_8A_FF_18_FE.a2dp_sink
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_sink.98_52_3D_A3_C4_1B.a2dp_sink latency_msec=100
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_sink.F8:5C:7D:C7:B3:68.a2dp_sink latency_msec=100
pactl load-module module-loopback source=virtual_out.monitor sink=bluez_sink.F8_5C_7D_C7_B3_68.a2dp_sink latency_msec=100
sudo systemctl status raspotify
sudo systemctl enable raspotify
sudo systemctl start raspotify
sudo systemctl status raspotify
bluetoothctl
pactl list sinks short
nano interactive_startup.sh
rm interactive_startup.sh
nano interactive_startup.sh
chmod+x interactive_startup.sh
chmod +x ~/startup.sh
chmod +x ~/interactive_startup.sh
./interactive_startup.sh
nano interactive_startup.sh
chmod+x interactive_startup.sh
chmod +x ~/interactive_startup.sh
./interactive_startup.sh
./device_selector.py
pactl list sinks
pact list sinks short
pactl list sinks short
./device_selector.py
sudo apt-get update
sudo apt-get install git
git config --global user.name "BrooksWimer"
git config --global user.email "wimerbrooks@gmail.com"
git remote add origin https://github.com/BrooksWimer/SyncSonicPi
git remote add origin https://github.com/BrooksWimer/SyncSonicPi.git
git remote add origin git@github.com:BrooksWimer/SyncSonicPi.git
git init
git remote add origin git@github.com:BrooksWimer/SyncSonicPi.git
git remote -v
ls
git add .
git commit -m "adding my pi code"
git push -u origin master
ls -la ~/.ssh
ssh-keygen -t rsa -b 4096 -C "wimerbrooks@gmail.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa
cat ~/.ssh/id_rsa.pub
ssh -T git@github.com
git push -u origin master
sudo apt-get update
sudo apt-get install nodejs npm
npm install -g npm
mkdir my-pi-api && cd my-pi-api
npm init -y
npm install express
nano server.js
cd ..
ls
cat device_selector.py
cd my-pi-api
ls
rm server.js
pip install flask
cd ..
pip install flask
apt install python3-flask
python3 -m venv venv
source venv/bin/activate
pip install flask
nano api_server.py
hostname -I
cat api_server.py
python api_server.py
ls
nano api_server.py
python api_server.py
cat device_selector.py
ls
rm api_server.py
nano api_server.py
python api_server.py
bluetoothctl
python api_server.py
bluetoothctl
ls
python api_server.py
cat api_server.py
ls
cat pair_selected_devices.sh
nano pair_selected_devices.sh
python api_server.py
nano pair_selected_devices.sh
nano api_server.py
python api_server.py
pactl list sinks
ls
pactl list sinks
ls
source venv/bin/activate
python api_server.py
source venv/bin/activate
python api_server.py
bluetoothctl
sudo systemctl stop bluetooth
sudo systemctl start bluetooth
python api_server.py
pactl list sinks short
python api_server.py
pactl list sinks short
