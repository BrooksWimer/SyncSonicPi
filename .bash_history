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
source venv/bin/activate
python api_server.py
cat /etc/default/raspotify
sudo find / -type f -name "*raspotify*" 2>/dev/null
cat /usr/lib/systemd/system/raspotify.service
bluetoothctl
pactl list sinks short
python api_server.py
bluetoothctl
python api_server.py
sudo ufw status verbose
sudo iptables -L -n -v
sudo firewall-cmd --list-all
sudo nft list ruleset
python api_server.py
ls
cat connect_configuration.sh
nano connect_configuration.sh
python api_server.py
bluetoothctl
python api_server.py
bluetoothctl
nano list_bluetooth_ports.sh
chmod +x list_bluetooth_ports.sh
ls
cat api_server_backup.py
nano api_server_backup.py
python api_server.py
pactl list sinks
pactl list sinks short
python api_server.py
pactl list sinks
python api_server.py
nano api_server.py
python api_server.py
source venv/bin/activate
python api_server.py
source venv/bin/activate
python api_server.py
source venv/bin/activate
python api_server.py
cat api_server.py
bluetoothctl 
nano python_api.py
nano api_server.py
python api_server.py
bluetoothctl
python api_server.py
ls
cat connect_configuration.sh
git add .
git branch
git add .
git commit -m "created the ability to list already paired devices and optimized scanning flow. Next step is optimizing connection flow"
git push
git pull
git checkout master
git branch -d main
git branch -D main
git push origin --delete main
git pull
git fetch origin
git log HEAD..origin/master --oneline
git pull --no-rebase
git push
cat connect_configuration.sh
mv connect_configuration.sh connect_configuration_backup.sh
nano connect_configuration.sh
python api_server.py
chmod + x connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
cat server_api.py
cat api_server.py
mv connect_configuration.sh connect_configuration_backup.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
nano api_server.py
python api_server.py
cat api_server_backup.py
nano api_server.py
python api_server.py
nano api_server.py
python api_server.py
rfkill list bluetooth
ps aux | grep bluetoothd
sudo systemctl restart bluetooth
python api_server.py
sudo reboot
source venv/bin/activate
python api_server.py
bluetoothctl
mv connect_configuration.sh connect_configuration_backup.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
restart bluetooth
python api_server.py
kill "${BTCTL_PID}" 2>/dev/null || true
coproc BTCTL { bluetoothctl; }
ps -p "$BTCTL_PID"
kill 3185
ps -p "$BTCTL_PID"
python api_server.py
ps -p "$BTCTL_PID"
coproc BTCTL { bluetoothctl; }
kill 3217
coproc BTCTL { bluetoothctl; }
kill 3219
coproc BTCTL { bluetoothctl; }
kill "$BTCTL_PID
kill "$BTCTL_PID
kill "$BTCTL_PID
kill 3221

kill 3221
jobs -l
pkill bluetoothctl
bluetoothctl
sudo systemctl status bluetooth
sudo systemctl stop bluetooth
sudo systemctl status bluetooth
sudo systemctl start bluetooth
bluetoothctl
sudo systemctl restart bluetooth
bluetoothctl show
devices
bluetoothctl devices
bluetoothctl
bluetoothctl show
pgrep -l bluetoothctl
sudo reboot
bluetoothctl
source venv/bin/activate
python api_server.py
connect_configuration.sh
cat connect_configuration.sh
rm connect_configuration.sh
nano connect_configuration.sh
python api_server.py
chmod +x connect_configuration.sh
pkill bluetoothctl
jobs -l
coproc BTCTL { bluetoothctl; }
kill 4618
coproc BTCTL { bluetoothctl; }
kill 4620
coproc BTCTL { bluetoothctl; }
kill "$BTCTL_PID"
wait "$BTCTL_PID" 2>/dev/null
exec {BTCTL[0]}>&-
kill "$BTCTL_PID"
wait "$BTCTL_PID" 2>/dev/null
exec {BTCTL[0]}>&-
exec {BTCTL[1]}>&-
coproc BTCTL { bluetoothctl; }
kill "$BTCTL_PID"
wait "$BTCTL_PID" 2>/dev/null
# Option 1: Direct syntax (requires Bash 4.2+)
# exec {BTCTL[0]}>&-
# exec {BTCTL[1]}>&-
# Option 2: Using eval if the above gives "ambiguous redirect"
eval "exec ${BTCTL[0]}>&-"
eval "exec ${BTCTL[1]}>&-"
coproc BTCTL { bluetoothctl; }
ps -p "$BTCTL_PID"
pgrep -l bluetoothctl
coproc BTCTL { bluetoothctl; }
jobs -l
echo "$BTCTL_PID"
coproc BTCTL { bluetoothctl; }
pkill -f bluetoothctl
pkill -f bluetoothd
coproc BTCTL { bluetoothctl; }
trap "echo 'Killing all child processes...'; kill $(jobs -p)" EXIT
coproc BTCTL { bluetoothctl; }
python api_server.py
kill -9 $(jobs -p)
coproc BTCTL { bluetoothctl; }
disown -a
jobs
pgrep -l bluetoothctl
kill -9 $(jobs -p)
disown -a
exec bash
pkill -9 bluetoothctl
coproc BTCTL { bluetoothctl; }
ls
cat api_server
cat api_server.py
ls
python -m venv benv
source benv/bin/activate
pip install dbus-fast
vim ble_server.py
vi ble_server.py
cat ble_server.py 
sudo python3 ble_server.py 
sudo python ble_server.py 
pip install dbus-fast
python -m pip install dbus-fast
python ble_server.py 
vi ble_server.py 
python ble_server.py 
vi ble_server.py 
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py 
sudo python ble_server.py 
sudo python -m pip install dbus-fast
apt install python3-dbus-fast
sudo apt install python3-dbus-fast
sudo python ble_server.py 
rm -rf ble_server.py 
vi ble_server.py
sudo python ble_server.py 
rm -rf ble_server.py 
vi ble_server.py
sudo python ble_server.py 
systemctl status bluetooth
ps aux | grep bluetoothd
sudo systemctl stop bluetooth
sudo bluetoothd --experimental &
bluetoothctl list
sudo python ble_server.py 
busctl tree org.bluez
dbus-send --system --print-reply --dest=org.bluez / org.freedesktop.DBus.Introspectable.Introspect
bluetoothctl list
busctl tree org.bluez
rm -rf ble_server.py 
vi ble_server.py
sudo python ble_server.py 
import asyncio
import dbus_fast.aio
from dbus_fast import Variant, DBusError
class BLEServer:
async def main():
if __name__ == "__main__":;     asyncio.run(main())
rm -rf ble_server.py
vi ble_server.py
sudo python ble_server.py 
rm -rf ble_server.py 
vi ble_server.py
sudo python ble_server.py 
systemctl status bluetooth
sudo systemctl start bluetooth
sudo systemctl restart bluetooth
systemctl status bluetooth.service
ps aux | grep bluetoothd
sudo killall bluetoothd
sudo systemctl restart bluetooth
ps aux | grep bluetoothd
systemctl status bluetooth
sudo python ble_server.py 
sudo nano /lib/systemd/system/bluetooth.service
import useBLE from "@/hooks/useBLE";
sudo systemctl daemon-reload
sudo systemctl restart bluetooth
systemctl status bluetooth
sudo python ble_server.py 
groups $USER
sudo usermod -aG bluetooth $USER
exit
groups $USER
source benv/bin/activate
ls
bluetoothctl
pip install pydbus
rm -rf ble_server.py 
vi ble_server.py
ls
cat connect_configuration.sh 
ps aux | grep bluetoothd
exit
bluetoothctl
ps
sudo systemctl restart bluetooth
ps
kill 4713
ps
kill 4701
kill 4914
ps
bluetoothctl
source venv/bin/activate
python api_server.py
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
nano testing.sh
chmod +x testing.sh
testing.sh
./bluetooth_report.sh
./testing.sh
rm testing.sh
nano testing.sh
chmod +x testing.sh
./testing.sh
rm testing.sh
nano testing.sh
chmod +x testing.sh
./testing.sh
cat connect_configuration.sh
rm connect_configuratino.sh
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
cat connect_configuration_backup.sh
rm connect_configuration.sh
nano connect_configuration.sh
python api_server.py
chmod +x connect_configuration.sh
python api_server.py
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
mv connect_configuration.sh gameplan.sh
nano apply_gameplan.sh
nano gameplan.json
./apply_gameplan.sh gameplan.json
chmod +x apply_gameplan.sh
./apply_gameplan.sh gameplan.json
nano apply_gameplan.sh
cat connect_configuration_backup.sh
rm apply_gameplan.sh
nano apply_gameplan.sh
chmod +x apply_gameplan.sh
./apply_gameplan.sh gameplan.json
rm apply_gameplan.sh
nano apply_gameplan.sh
chmod +x apply_gameplan.sh
./apply_gameplan.sh gameplan.json
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
nano connect_configuration.sh
python api_server.py
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
nano connect_configuration.sh
python api_server.py
cat apply_gameplan.sh
rm apply_gameplan.sh
nano apply_gameplan.sh
chmod +x apply_gameplan.sh
python api_server.py
ps
rm apply_gameplan.sh
nano apply_gameplan.sh
python api_server.py
chmod +x apply_gameplan.sh
python api_server.py
rm apply_gameplan.sh
nano apply_gameplan.sh
chmod +x apply_gameplan.sh
python api_server.py
nano apply_gameplan.sh
python api_server.py
bluetoothctl
chmod +x apply_gameplan.sh
nano apply_gameplan.sh
python api_server.py
nano apply_gameplan.sh
pip install pydbus
python api_server.py
apply_gameplan.py
nano apply_gameplan.py
cat connect_configuration.sh
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
sudo apt-get update
sudo apt-get install python3-gi
python api_server.py
cd ..
python3 -m venv --system-site-packages venv
ls
cd syncsonic
ls
python3 -m venv --system-site-packages venv
python api_server.py
nano apply_gameplan.py
cat apply_gameplan.py
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
ps
python api_server.py
nano connect_configuration.sh
rm connect_configuration.sh
nano connect_configuration.sh
chmod +x connect_configuration.sh
python api_server.py
select 2C:CF:67:CE:57:91
bluetoothctl 2C:CF:67:CE:57:91
bluetoothctl select 2C:CF:67:CE:57:91
bluetoothctl
nano apply_gameplan.py
python api_server.py
nano apply_gameplan.py
cat apply_gameplan.py
rm apply_gameplan.py
nano apply_gameplan.py
chmod +x apply_gameplan.py
python api_server.py
bluetoothctl
ps
bluetoothctl
nano apply_gameplan.py
python api_server.py
hciconfig -a
sudo systemctl restart bluetooth
hciconfig -a
sudo hciconfig hci2 down
sudo hciconfig hci2 up
sudo hciconfig hci2 reset
subo reboot
reboot
sudo reboot
source benv/bin/activate
pip install bluezero
pip install pydbus
ls
vi ble_server.py
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py 
pip install gi
python ble_server.py 
rm -rf ble_server.py 
pip install dbus-next
vi ble_server.py
python ble_server.py
pip install dbus
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py 
sudo apt-get install python3-dbus
python ble_server.py 
pip install dbus-python
sudo apt-get install bluetooth bluez python3-dbus libdbus-1-dev l
pip install dbus-python
python ble_server.py 
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
bluetoothctl --version
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
pip install gobject
python ble_server.py
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
pip install bluezero
sudo apt-get install python3-bluezero
sudo apt-get install cmake
pip install bluezero
sudo apt-get install cairo
sudo apt-get install libcairo2-dev pkg-config python3-dev
pip install bluezero
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
sudo apt-get install python3-gi
mkdir ble_gatt_server
cd ble_gatt_server/
vi gatt_server.py
cd ..
nano ble_server.py 
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
rm -rf ble_server.py 
vi ble_server.py
python ble_server.py
go
sudo apt-get install golang
go
rm -rf ble_server.py 
rm -rf ble_gatt_server/gatt_server.py 
vi ble_gatt_server/gatt_server.go
vi ble_server.go
vi go.mod
go mod download
go build -o ble_server
rm -rf go.mod
ls
rm -rf go.sum
rm -rf ble_server.go 
vi ble_server.go
go build -o ble_server
go mod init
vi go.mod
go mod tidy
go build -o ble_server
go mod tidy
vi go.mod
go mod tidy
go build -o ble_server
./ble_server 
rm -rf ble_server.go 
ls
vi ble_server.go
go build -o ble_server
./ble_server 
rm -rf ble_server.go
vi ble_server.go
go build -o ble_server
./ble_server 
systemctl status bluetooth
busctl tree org.bluez | grep GattManager1
hciconfig hci0 down
hciconfig hci0 up
sudo hciconfig hci0 down
sudo hciconfig hci0 up
sudo ./ble_server 
bluetoothctl show
rm -rf ble_server.go
vi ble_server.go
go build -o ble_server
sudo ./ble_server 
rm -rf ble_server.go
vi ble_server.go
go build -o ble_server
sudo ./ble_server 
./ble_server 
rm -rf ble_server.go
vi ble_server.go
go build -o ble_server
rm -rf ble_server.go
vi ble_server.go
go build -o ble_server
./ble_server 
sudo ./ble_server 
sudo systemctl status bluetooth
bluetoothctl
bluetoothctl --version
busctl tree org.bluez
busctl introspect org.bluez /org/bluez/hci0 | grep GattManager1
sudo systemctl restart bluetooth
busctl introspect org.bluez /org/bluez/hci0 | grep GattManager1
busctl introspect org.bluez /org/bluez/hci0
sudo ./ble_server 
rm -rf ble_server.go 
vi ble_servergo
vi ble_server.go
go build -o ble_server
sudo ./ble_server 
rm -rf ble_server.go 
vi ble_server.go
go build -o ble_server
sudo ./ble_server 
rm -rf ble_server.go 
vi ble_server.go
go build -o ble_server
rm -rf ble_server.go 
vi ble_server.go
go build -o ble_server
sudo ./ble_server 
sudo systemctl status bluetooth
busctl list org.bluez
busctl list
bluetoothctl
