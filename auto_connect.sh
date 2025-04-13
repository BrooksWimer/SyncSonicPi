#!/bin/bash
set -e

HCI_INTERFACE="hci0"
HCI_MAC=$(hciconfig $HCI_INTERFACE | grep "BD Address" | awk '{print $3}')

if [[ -z "$HCI_MAC" ]]; then
  echo "❌ Could not retrieve MAC for $HCI_INTERFACE"
  exit 1
fi

/usr/bin/expect <<EOF
log_user 1
set timeout -1
set idle_timeout 20
set last_prompt_time [clock seconds]
set paired_success 0

proc send_and_expect {cmd success_msg {alt_msg ""}} {
    for {set i 0} {\$i < 3} {incr i} {
        send "\$cmd\r"
        expect {
            -re \$success_msg {
                puts "✅ \$cmd succeeded"
                return 0
            }
            -re \$alt_msg {
                puts "⚠️ \$cmd: already satisfied"
                return 0
            }
            -re "Failed.*" {
                puts "❌ \$cmd failed, retrying (\$i)..."
                sleep 2
                continue
            }
            -re "# $" {
                puts "⚠️ \$cmd got shell prompt without success — retrying"
                sleep 2
                continue
            }
            timeout {
                puts "⏳ \$cmd timed out, retrying (\$i)..."
                sleep 2
                continue
            }
        }
    }
    puts "🚨 \$cmd failed after 3 attempts — exiting"
    exit 1
}

spawn bluetoothctl
expect -re "# $"

send_and_expect "select $HCI_MAC" "Controller $HCI_MAC.*"
send_and_expect "power on" "Changing power on succeeded"
send_and_expect "agent NoInputNoOutput" "Agent registered" "Agent is already registered"
send_and_expect "default-agent" "Default agent request successful"
send_and_expect "discoverable on" "Changing discoverable on succeeded"
send_and_expect "pairable on" "Changing pairable on succeeded"

# Handle prompts (passkey confirmation)
while {1} {
    puts "🔁 Waiting for pairing prompts or timeout..."
    expect {
        -re {Confirm passkey.*\(yes/no\):} {
            set last_prompt_time [clock seconds]
            send "yes\r"
            exp_continue
        }
        -re {Authorize service.*\(yes/no\):} {
            set last_prompt_time [clock seconds]
            send "yes\r"
            set paired_success 1
            exp_continue
        }
        -re {^\[.*\]} {
            # Some bluetoothctl status line — reset idle
            set last_prompt_time [clock seconds]
            exp_continue
        }
        timeout {
            set now [clock seconds]
            set idle_time [expr {$now - $last_prompt_time}]
            puts "⏳ Idle for $idle_time seconds (limit: $idle_timeout)..."
            if {$idle_time >= $idle_timeout} {
                puts "\n✅ No activity for $idle_timeout seconds — exiting bluetoothctl."
                send "exit\r"
                expect {
                    eof { exit $paired_success }
                    timeout { puts "⚠️ Failed to exit cleanly. Forcing exit."; exit $paired_success }
                }
            } else {
                exp_continue
            }
        }
    }
}

EOF
