SyncSonicPi
Project Overview and Purpose
SyncSonicPi is a Raspberry Pi-based backend system that turns your Pi into a multi-speaker Bluetooth audio hub. It allows a Raspberry Pi (Zero, 4, etc.) to connect to multiple Bluetooth speakers simultaneously and receive control commands from a mobile application via Bluetooth Low Energy (BLE). In essence, a smartphone can connect to the Pi over BLE (low-bandwidth control channel) to manage audio playback, volume, and speaker grouping, while the Pi handles high-quality audio streaming to several Bluetooth speakers in sync. This creates a multi-room or stereo audio system using inexpensive Bluetooth speakers, coordinated by the Pi. At a high level, SyncSonicPi’s architecture consists of:
A BLE Control Interface (Python service): Runs on the Raspberry Pi’s built-in Bluetooth adapter. It advertises a BLE GATT service that the mobile app connects to. The phone can send commands (e.g., add/remove a speaker, adjust volume) through this interface. The code for this is in the syncsonic_ble Python package (with main.py as the entry point).
Multiple Bluetooth Audio Outputs: The Pi connects to multiple Bluetooth speakers using additional Bluetooth adapters (usually USB dongles). Each speaker is a Bluetooth A2DP sink managed by PulseAudio on the Pi. PulseAudio routes the audio stream to all connected speakers, keeping them as synchronized as possible.
Backend Orchestration Scripts: Shell scripts and a systemd service ensure that all Bluetooth adapters are initialized and healthy, PulseAudio is running in a headless mode, and the Python BLE service starts on boot. This makes the system largely hands-off once set up.
Overall, the Raspberry Pi acts as a central hub: receiving control commands from the phone over BLE using the built-in adapter, and streaming audio output to multiple speakers via the USB Bluetooth adapters. The use of PulseAudio handles the audio routing and synchronization across speakers, abstracting away many low-level audio quirks of the Raspberry Pi and Bluetooth.
Hardware Requirements and Setup
Raspberry Pi: You can use a Raspberry Pi Zero W, Raspberry Pi 4, or a similar model with Bluetooth capability. The Pi’s internal Bluetooth (onboard UART-based adapter) will be dedicated to the BLE control connection with the phone. For connecting to multiple speakers simultaneously, you will need additional Bluetooth adapters:
USB Bluetooth Dongles: Acquire as many USB Bluetooth adapters as the number of speakers you want to stream to (one adapter can typically maintain one high-quality audio stream reliably). For example, to stream audio to 3 speakers, you might use the built-in adapter for BLE and 3 USB adapters for the speakers.
USB Hub (Optional but Recommended): If using a Pi Zero (which has only one USB OTG port) or if you need multiple USB adapters on any Pi, use a powered USB hub. A powered hub ensures adequate power to all Bluetooth dongles and can help avoid dropouts. The hub also makes it possible to reset all adapters in one go (the project includes a script to “power cycle” the hub if some adapters misbehave).
Power Supply: Make sure your Raspberry Pi has a stable power supply. Streaming audio and driving multiple radios can be power-intensive, so a good 5V supply is needed to avoid brown-outs or Wi-Fi/Bluetooth instability.
Bluetooth Adapter Roles: The key to SyncSonicPi’s hardware setup is distinguishing the Pi’s internal Bluetooth from the external USB dongles:
The built-in Bluetooth adapter (on the Pi’s UART bus, usually hci0) is reserved for the BLE connection to the phone. This ensures the control channel is always available and not congested by audio streaming.
The USB Bluetooth adapters (on the USB bus, e.g. hci1, hci2, etc.) are used to connect to Bluetooth speakers for audio streaming. Using multiple adapters in parallel allows simultaneous A2DP audio output to multiple devices.
On startup, the system will automatically identify the built-in (UART) adapter versus USB adapters and label them accordingly. For example, the initialization script will check each hci interface’s bus type and reserve the UART one for BLE
file-ny2mr53mv6lx1x6souewhn
. It even renames the adapters for clarity: the reserved built-in adapter gets a Bluetooth device name like "Sync-Sonic" (so your phone sees a device with that name)
file-ny2mr53mv6lx1x6souewhn
, while the USB adapters get names like "raspberrypi-1", "raspberrypi-2", etc., for easy identification
file-ny2mr53mv6lx1x6souewhn
. This naming is mostly cosmetic, but it helps confirm which adapters are which when you scan for devices. Note: If you use a Pi Zero W, you’ll connect your USB Bluetooth dongles through the Pi’s micro-USB OTG port via a USB hub. If you use a Pi 4 or another model with multiple USB ports, you can plug the adapters directly. In either case, if you have many adapters, placing them on a USB extender or hub ports spaced apart can sometimes improve radio performance by reducing interference between adapters.
Software Prerequisites
Before installing SyncSonicPi, ensure your Raspberry Pi OS is prepared with the necessary software:
Operating System: Raspberry Pi OS (Raspbian) – both the Lite (headless) or Desktop versions are fine. This guide assumes a recent version (Bullseye or newer). Older versions might not have PulseAudio by default, but we can install it.
Bluetooth Stack: BlueZ (the Linux Bluetooth stack) should already be installed on Raspberry Pi OS. (If not, install it with sudo apt-get install bluetooth bluez).
PulseAudio: This project uses PulseAudio as the sound server (instead of the default ALSA or BlueALSA). PulseAudio provides the ability to manage multiple audio sinks and route audio between them. If you’re on Raspberry Pi OS with Desktop (Bullseye+), PulseAudio is likely already the default sound server. On Lite editions or older releases, you’ll need to install it:
bash
Copy
Edit
sudo apt-get update
sudo apt-get install pulseaudio pulseaudio-module-bluetooth
The pulseaudio-module-bluetooth package is important – it provides PulseAudio with Bluetooth A2DP support (modules to discover and handle Bluetooth audio devices). Without it, PulseAudio won’t know how to work with Bluetooth speakers.
Python 3: The backend code is written in Python 3. Raspberry Pi OS ships with Python 3 by default. You can verify by running python3 --version. We also recommend installing pip and venv if not already present:
bash
Copy
Edit
sudo apt-get install python3-pip python3-venv
Python Libraries: The Python code relies on a few libraries for DBus and GObject integration:
python-dbus (or dbus-python): Provides the dbus module in Python, used to interact with the BlueZ D-Bus API for BLE and device management.
PyGObject (GObject Introspection for GLib/GIO): Provides the gi.repository (used for GLib main loop to handle asynchronous events in the BLE service).
These can be installed via apt or pip. On Raspberry Pi OS, you can install via apt:
bash
Copy
Edit
sudo apt-get install python3-dbus python3-gi
Alternatively, in a Python virtual environment, you can use pip:
bash
Copy
Edit
pip install dbus-python PyGObject
Note: Installing PyGObject via pip requires development libraries on the system (GLib, etc.). Using the apt packages as shown above might be easier. If you use the apt method, you may still use a virtual environment with the --system-site-packages option, or simply run the app with the system interpreter. For simplicity, ensure the above packages are installed system-wide.
Installation and Setup
1. Obtain the SyncSonicPi Code
Download or clone the SyncSonicPi project to your Raspberry Pi. (If this came as a zip or git repository, extract it to a directory, e.g., /home/pi/syncsonic/). The project structure should look roughly like:
bash
Copy
Edit
syncsonic/
├── syncsonic_ble/        # Python package for BLE and audio control
│   ├── main.py
│   ├── ... (other Python modules)
├── reset_bt_adapters.sh  # Shell script to manage Bluetooth adapters
├── pulse-headless.pa     # PulseAudio headless configuration
├── start_syncsonic.sh    # Shell script to start the whole backend
└── syncsonic.service     # Systemd service unit file
2. Set Up a Python Virtual Environment (optional but recommended)
It’s good practice to run the Python code in a virtual environment to isolate its dependencies:
bash
Copy
Edit
cd ~/syncsonic
python3 -m venv venv
source venv/bin/activate
pip install dbus-python PyGObject   # install required libraries in venv
If the pip install for any library fails, ensure you installed the system packages mentioned in prerequisites (e.g., python3-dbus and python3-gi). You can also install other needed packages as they appear (for example, if a requirements.txt is provided with the project, use pip install -r requirements.txt). After installing, ensure that you can run the main program. Try:
bash
Copy
Edit
python3 -m syncsonic_ble.main
This shouldn’t actually fully run the service yet (since we might not have PulseAudio and adapters configured in this step), but if it launches without import errors and then complains about missing environment or adapters, it means the environment is set up correctly. You can press Ctrl+C to stop it for now. (We will set it up to run on boot later.) Deactivate the venv for now (deactivate command) and continue setup.
3. Configure PulseAudio for Headless Operation
For multi-speaker audio, PulseAudio will be run in “headless” mode (no GUI session). We provide a PulseAudio configuration file pulse-headless.pa that loads the necessary modules and sets up a suitable audio routing:
It will load the Bluetooth discovery and policy modules so PulseAudio can automatically detect and manage Bluetooth A2DP devices.
It may define a virtual audio sink or combine sink for multi-speaker output (so that one audio stream can play on all speakers).
It disables any modules that require an X11 display or UI (since this is a headless use-case), ensuring PulseAudio runs purely in the background.
Install the PulseAudio config:
You can copy pulse-headless.pa to a known location (e.g., /etc/pulse/pulse-headless.pa or keep it in the project directory). In our launch script, we will reference this file when starting PulseAudio. For example, the start script might invoke PulseAudio as:
bash
Copy
Edit
pulseaudio --start --file=/path/to/pulse-headless.pa
This tells PulseAudio to daemonize (--start) and load the given configuration file instead of the default. Ensure the path to pulse-headless.pa in the script or service file is correct for where you put it. If you want to verify, you can manually run:
bash
Copy
Edit
pulseaudio --start --file=./pulse-headless.pa
and then run pactl info. You should see that PulseAudio is running (Server Name etc.). You should also see that module-bluetooth-discover is loaded by running pactl list modules short | grep bluetooth. If not, double-check the configuration file and PulseAudio logs.
4. Understand and Configure Key Components
Now let’s go through the main components of the codebase and configuration, and what (if anything) you might need to configure for your setup:
syncsonic_ble/main.py: This is the Python entry point for the BLE service. It sets up the BLE advertising and GATT server by calling into the transport/gatt_server.py module. When launched, it will:
Initialize the D-Bus main loop and BlueZ interfaces.
Find the reserved Bluetooth adapter (expected from an environment variable) to use for BLE advertising.
Register a BLE GATT service (custom) and characteristic that the mobile app can use to send commands. For example, there is a Volume endpoint (see endpoints/volume.py) which likely allows the phone to set the volume on the speakers.
Set up a pairing agent (so the phone can pair/bond if needed for BLE) and make the device discoverable as "Sync-Sonic".
Internally, it also calls setup_pulseaudio() at startup to ensure PulseAudio is running and ready. This function checks if PulseAudio is responsive and, if not, attempts to start it or restart it.
Once running, it enters the GLib event loop to handle BLE events (connections, incoming commands). The BLE interface is the “brain” that reacts to the mobile app (e.g., telling the system to scan for new speakers, connect/disconnect speakers, change volume, etc.).
Note: syncsonic_ble/constants.py expects an environment variable RESERVED_HCI (the reserved adapter name, like hci0) to be set; if it’s not set, the program will raise an error on startup to avoid using the wrong adapter【18†】. We’ll see how this variable gets set next.
reset_bt_adapters.sh: This Bash script ensures all Bluetooth adapters are present and in a healthy state before we start the BLE service or audio streaming. It performs several important tasks:
Adapter Health Check: It looks for all available hci interfaces (using hciconfig) and compares the count to the expected number of adapters. By default, it expects 4 adapters
file-ny2mr53mv6lx1x6souewhn
 (you can override by passing a number as an argument). If some adapters are missing or unresponsive (e.g., showing an invalid MAC address of 00:00:00:00:00:00), the script will attempt to reset them.
USB Hub Power Cycle: If it detects missing adapters, it will power-cycle the USB hub at path 1-1 by unbinding and rebinding the USB hub driver
file-ny2mr53mv6lx1x6souewhn
. This effectively turns the hub (and devices on it) off and on, which can bring back devices that disappeared (a common occurrence with some USB Bluetooth dongles on boot). The HUB_PATH="1-1" is the default root hub on the Pi’s USB bus
file-ny2mr53mv6lx1x6souewhn
 – you may adjust this in the script if your adapters are on a different hub path.
Resetting Individual Adapters: For adapters that are present but have an invalid address (sometimes a sign they need a reset), the script will unbind and rebind the specific USB device for that adapter
file-ny2mr53mv6lx1x6souewhn
. This is a more targeted reset (instead of the whole hub).
Bringing Adapters Up: After power-cycles/resets, the script ensures each adapter’s interface (hciX) is powered up (hciconfig hciX up)
file-ny2mr53mv6lx1x6souewhn
. This is retried a few times if needed.
Identifying the UART (Phone) Adapter: Once the expected adapters are all healthy, the script identifies which one is the built-in Bluetooth. It does this by checking the “Bus” type of each adapter via hciconfig. If the bus type is UART, that adapter is the internal one (e.g., hci0 on a Pi) – the script marks this one as RESERVED for the phone/BLE
file-ny2mr53mv6lx1x6souewhn
. It even sets the Bluetooth device name of that adapter to "Sync-Sonic" for easy identification when scanning on your phone
file-ny2mr53mv6lx1x6souewhn
. All other adapters (which will be USB bus type) are assumed to be for speakers and get named raspberrypi-1, raspberrypi-2, etc. in sequence
file-ny2mr53mv6lx1x6souewhn
 (so if you see devices with those names when scanning from a speaker or another system, you know they are the Pi’s audio outputs).
Setting Environment Variable: The script then writes the reserved adapter’s identifier to /etc/default/syncsonic as an environment variable
file-ny2mr53mv6lx1x6souewhn
. For example, if hci0 is the built-in reserved adapter, it will write:
bash
Copy
Edit
export RESERVED_HCI=hci0
in the file /etc/default/syncsonic. This file will be used by the systemd service or start script to load that environment variable so that the Python code knows which adapter to use for BLE
file-ny2mr53mv6lx1x6souewhn
.
This script should be run at boot (before launching the Python service). Typically, the start_syncsonic.sh or the systemd service will call this script. You can adjust the EXPECTED_ADAPTER_COUNT in the script (or pass a parameter) if you plan to use a different number of adapters. For example, if you only use 2 USB dongles (plus 1 internal = 3 total), you can call reset_bt_adapters.sh 3 in the start script. The script is quite robust: it will loop until all expected adapters are up and healthy, performing resets as needed, so it may take a few seconds at boot, but it ensures a reliable start.
pulse-headless.pa: This is a PulseAudio configuration file tailored for running PulseAudio without a GUI and for multi-Bluetooth-speaker output. Key aspects of this config likely include:
Bluetooth Modules: It loads module-bluetooth-policy and module-bluetooth-discover, which allow PulseAudio to automatically detect new Bluetooth audio devices and manage stream policy (like switching audio to the device when connected).
Combined/Virtual Sink: It may set up a combined sink or a null sink + loopbacks. For instance, one strategy is to create a null sink (virtual audio output) that acts as the central audio source, and then for each Bluetooth speaker connected, a loopback module routes the audio from the null sink to that speaker’s sink. This way, any audio played to the null sink will be heard on all Bluetooth speakers. Another strategy is using module-combine-sink to group all Bluetooth sinks into one output. The exact method can be seen in the config file. The goal is to handle the fact that PulseAudio normally treats each Bluetooth speaker as a separate sink; we want a way to play one stream to multiple sinks.
Headless Settings: It likely disables module loading that requires X11 or uses GUI (e.g., no volume control UIs, etc.), and might enable module-native-protocol-unix for clients (so that the Python service or other processes can send audio to Pulse if needed, without needing an X session).
Using the PulseAudio config: If you installed PulseAudio via apt, the system might by default use ~/.config/pulse/default.pa or /etc/pulse/default.pa. You do not want to override the system default if you also use the Pi for other purposes, so it’s better to explicitly start PulseAudio with this custom file. Our start script does that with the pulseaudio --start --file=pulse-headless.pa command. You should ensure PulseAudio uses this file on boot (either via the script or by updating the service). No manual changes in pulse-headless.pa are required unless you have custom audio routing needs. However, feel free to open the file to see the modules it loads. For example, you should see lines like:
ini
Copy
Edit
load-module module-bluetooth-discover
load-module module-bluetooth-policy
# (possibly a load-module module-null-sink or combine-sink here)
and at the end perhaps setting a default sink. This is all pre-configured to make multi-speaker audio work out-of-the-box.
start_syncsonic.sh: This is the main launcher script that ties everything together. When you enable SyncSonicPi on boot, this script will be executed (via systemd). What it typically does:
Reset Adapters: It calls reset_bt_adapters.sh (possibly with an argument for how many adapters to expect) to perform the Bluetooth adapter setup as described above. This must complete (all adapters ready) before proceeding.
Start PulseAudio: It then launches PulseAudio in headless mode. Usually:
bash
Copy
Edit
pulseaudio --start --file=/path/to/pulse-headless.pa
This ensures the PulseAudio daemon is running and ready to accept Bluetooth connections. The script might include a short delay or a loop to verify PulseAudio started (though our Python code also double-checks this).
Launch the BLE Service: Finally, it runs the Python BLE server. For example:
bash
Copy
Edit
python3 -m syncsonic_ble.main
(If using a virtual environment, it might activate that or use the venv’s python interpreter here.) Because the script is likely run as the pi user (see syncsonic.service below), it should source the environment variable for RESERVED_HCI before calling Python. If the service file uses EnvironmentFile=/etc/default/syncsonic, the variable will already be in the environment. If not, the script itself might do something like . /etc/default/syncsonic to load that variable. This ensures that syncsonic_ble.main knows which HCI to use for BLE.
This script doesn’t require user modifications in most cases. Just ensure the paths inside it are correct (for example, if you placed files in a different directory, update the script accordingly). Also, ensure it has execute permission (chmod +x start_syncsonic.sh). You can test run this script manually to make sure each step works before enabling the service.
syncsonic.service: This is a systemd unit file that makes SyncSonicPi start on boot and stay running. By installing this file and enabling the service, you ensure that every time the Pi boots, the backend will initialize and start listening for the phone app automatically. Let’s break down important contents of this service file:
Unit Description and Dependencies: It likely has a description like “SyncSonicPi Service” and After=bluetooth.target sound.target to make sure Bluetooth and sound systems are up before it starts. It might also have Wants=bluetooth.target.
Service Section:
Type=simple (since our start script runs the process in the foreground).
User=pi: The service might be set to run as the pi user (or whichever user you prefer) rather than root. This is because PulseAudio is typically best run as a normal user. Running as pi also means the environment will be that user’s, and PulseAudio will use the user’s runtime directory. (By default, Raspberry Pi OS has the pi user in the bluetooth and audio groups, which is needed for Bluetooth and audio access. Ensure your user is in those groups if you changed the username.)
EnvironmentFile=/etc/default/syncsonic: This line pulls in the RESERVED_HCI variable that reset_bt_adapters.sh writes. Systemd will load that and make it available to the start script/Python process
file-ny2mr53mv6lx1x6souewhn
. This is how the Python code knows which adapter to use for BLE without hard-coding it.
ExecStart: The command to run when starting the service. This will point to the start_syncsonic.sh script, for example:
ini
Copy
Edit
ExecStart=/home/pi/syncsonic/start_syncsonic.sh
(Make sure the path is correct for where you put the files, and that the script is executable.)
Restart=on-failure: This ensures that if the service crashes or exits with an error, systemd will try to restart it after a delay. This is good for resilience (if something goes wrong, it will attempt to recover).
Optionally, there might be ExecStartPre directives instead of a separate start script – but in our design, we use the script to handle multiple steps. If using start_syncsonic.sh, we typically don’t need separate ExecStartPre commands.
Install Section: This has WantedBy=multi-user.target which means the service will start during the normal multi-user boot (standard for background services on Pi OS).
Setting up the service:
Copy syncsonic.service to /etc/systemd/system/syncsonic.service (or create a symlink if you’re developing). Adjust the file paths inside it if needed (especially the path to the ExecStart script and the EnvironmentFile, if those are in non-standard locations).
Reload systemd to pick up the new service file:
bash
Copy
Edit
sudo systemctl daemon-reload
Enable the service to start on boot:
bash
Copy
Edit
sudo systemctl enable syncsonic.service
(Optional) Start the service immediately without rebooting, for testing:
bash
Copy
Edit
sudo systemctl start syncsonic.service
Check status with sudo systemctl status syncsonic.service to see if it started properly. The first run might take a bit due to adapter resets. If it’s active (running), you’re all set. If it failed, examine the logs (see Troubleshooting below).
With the systemd service in place, your SyncSonicPi backend will automatically initialize on boot, run the adapter check, start PulseAudio, and launch the BLE control server.
Usage: Operating SyncSonicPi
Once everything is installed and running, using the system is straightforward:
On Boot: The Raspberry Pi will automatically start advertising itself as a BLE peripheral named “Sync-Sonic” (thanks to our reserved adapter naming). The mobile app can find this BLE device and connect to it. The first time, you may need to pair the phone with the Pi (depending on how the app is set up). The SyncSonicPi code includes a pairing agent that should handle incoming pairing requests without requiring a PIN (it likely uses “NoInputNoOutput” capability for BLE).
Mobile App Control: With the phone connected over BLE, you can use the app to issue commands. For example, the app might have a feature to scan for available Bluetooth speakers nearby – when triggered, the Pi’s backend will use BlueZ to scan via the USB adapters and list found speaker devices. Then, when you select a speaker to connect, the backend (via connect_planner and device_manager in the code) will initiate pairing/connection to that speaker using one of the free USB Bluetooth adapters.
Audio Streaming: The actual audio source can vary. In one scenario, the phone could stream music to the Pi (though BLE can’t handle high-quality audio streams; more likely the phone might send a URL or command to the Pi to play a certain song from a server or the Pi’s storage). Another scenario is the Pi could be running a music service or playing local media autonomously, and the phone just controls which speakers are active and the volume. By default, PulseAudio will route all system audio to the connected Bluetooth sinks. If you play any sound on the Pi (for example, using a media player or even paplay), it should output on the Bluetooth speakers.
Multi-Speaker Sync: The system uses PulseAudio to keep audio roughly in sync across speakers. All connected speakers either share a combined audio sink or are fed from the same source via loopbacks. This means when you play audio, each speaker should get the stream. PulseAudio’s combine/loopback mechanism will attempt to account for latency differences. In practice, Bluetooth inherent latency means there could be slight delay between speakers, but PulseAudio will try to minimize drift. For a test, try connecting two speakers and run:
bash
Copy
Edit
paplay /usr/share/sounds/alsa/Front_Center.wav
Both speakers should play the “Front Center” audio nearly simultaneously. If one is consistently ahead, you might need to adjust the strategy (this is an advanced PulseAudio configuration topic).
Volume Control: The mobile app likely has a master volume or per-speaker volume control. The SyncSonicPi BLE service has a volume endpoint which will translate BLE commands into PulseAudio volume adjustments. It might, for instance, set the volume on the combined sink or on each sink (the code’s endpoints/volume.py and related logic handle this). From the user perspective, adjusting volume on the app will raise/lower the sound output on the Bluetooth speakers through PulseAudio.
In normal operation, you won’t have to interact with the Raspberry Pi directly – the phone app and the automated service handle everything. The Pi is headless and can be tucked away with the speakers, and you use the app to control power, volume, and sources.
Troubleshooting Tips
Even with the best setup, you might encounter some hiccups. Here are some common issues and how to address them:
Service fails to start / exits: If syncsonic.service isn’t staying active, check its logs:
bash
Copy
Edit
sudo journalctl -u syncsonic.service -f
This will show live logs from our scripts and Python service (the code is set to DEBUG logging to stdout by default【29†】). Look for messages. For example, if you see “No UART adapter found; RESERVED_HCI left unset” or a RuntimeError about RESERVED_HCI not set, cannot pick phone adapter, it means the adapter reset script didn’t find the built-in Bluetooth. This could happen if the internal BT is hard-blocked (rfkill) or not present. Ensure the Pi’s Bluetooth is enabled. You might need to run sudo raspi-config to enable the interfacing option for Bluetooth if disabled, or check rfkill list to see if Bluetooth is blocked (unblock it with rfkill unblock bluetooth). Then reboot or rerun the service.
Missing USB adapters: If the log shows “Missing adapters. Hub cycle.”
file-ny2mr53mv6lx1x6souewhn
file-ny2mr53mv6lx1x6souewhn
 repeatedly, it means it expected more Bluetooth dongles than were found. Recount your adapters and ensure EXPECTED_ADAPTER_COUNT is set correctly. Also ensure all USB dongles are detected: run hciconfig or lsusb to see if they show up. If not, try unplugging/replugging them or use a powered hub. The script will retry indefinitely until it finds all adapters, so if you only have (for example) 2 adapters but it’s set to 4, it will never succeed. Solution: edit reset_bt_adapters.sh to set the correct number, or pass the number as an argument in the service or start script. For instance, in start_syncsonic.sh call reset_bt_adapters.sh 3 if you have 3 total adapters.
Bluetooth pairing issues with speakers: The first time connecting to a new speaker, the Pi will initiate pairing. Some speakers might require a PIN or confirmation. The SyncSonicPi agent uses a “just works” pairing (no PIN). If a speaker refuses to pair, you might need to put it in pairing mode manually. Watch the logs for messages about pairing or authentication. If needed, you can pre-pair a device by using bluetoothctl on the Pi for a test. Generally, once paired, the service should auto-reconnect on subsequent runs.
Speakers connect but no audio: If your phone app indicates speakers are connected (or you see in logs that devices connected), but you hear no sound:
Ensure PulseAudio is running: pactl info should show a server. If not, the Python code’s attempt to start PulseAudio might have failed. You can try running pulseaudio --start --file=/path/to/pulse-headless.pa manually to see any error messages. One common issue is if PulseAudio was already running under a different user or process. You may need to kill it (pulseaudio -k or even pkill pulseaudio) and let our service start it fresh.
Check sinks: Run pactl list sinks short. You should see entries like bluez_sink.xx_xx_xx... for each connected speaker, and possibly a null or combined sink if the config created one. If you only see individual sinks but audio isn’t coming, maybe the audio is being sent to a wrong sink. You might need to set the default sink to the combined one. In our setup, pulse-headless.pa likely already sets the default or uses module-combine-sink, but double-check. You can manually set default sink with pacmd set-default-sink <sink_name>.
Volume: It’s possible the volume on the sinks is low. Use pactl set-sink-volume <sink> 100% to raise volume or check if the volume endpoint from the app actually changed PulseAudio’s volume. You can also check pactl list sinks to see the volume levels.
Audio out-of-sync or choppy: Bluetooth audio inherently has latency. PulseAudio’s combine sink tries to keep streams in sync, but if one speaker has a much longer processing delay, perfect sync is hard. Minor echo effects can occur. If synchronization is critical, ensure all speakers use the same Bluetooth codec (SBC by default). Also, Wi-Fi interference or USB bandwidth issues can cause drops. Using a powered hub and keeping the Pi close to the speakers (or at least not blocked by many walls) helps. For choppy audio, it often means the bandwidth is an issue – having multiple Bluetooth streams can tax the Pi’s wireless throughput or USB controller. You might experiment with using 5 GHz Wi-Fi for the Pi (to avoid 2.4 GHz interference) or try fewer speakers to see if it improves. The good news is the software will automatically reconnect if a stream breaks (BlueZ/PulseAudio usually try to recover A2DP links).
Debugging further: You can increase logging or run the Python service in a console for more verbose output. Since logging.basicConfig(level=logging.DEBUG) is set【29†】, you should already see detailed logs. If you suspect an issue in the BLE control logic, you can add prints or more logs in the Python code (for advanced debugging). For Bluetooth-specific issues, bluetoothctl is a handy tool to scan and see device statuses outside our program.
Updating configuration: If you need to change the number of adapters, names, or PulseAudio settings, remember to update the relevant files and then restart the service:
bash
Copy
Edit
sudo systemctl restart syncsonic.service
If you changed syncsonic.service itself, do daemon-reload again before restarting.
