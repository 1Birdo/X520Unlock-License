import os
import subprocess
import sys

def run_command(cmd_list):
    try:
        subprocess.run(cmd_list, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(cmd_list)}")
        sys.exit(1)

# Unload and reload ixgbe module with unsupported SFP enabled
run_command(['sudo', 'modprobe', '-r', 'ixgbe'])
run_command(['sudo', 'modprobe', 'ixgbe', 'allow_unsupported_sfp=1'])

# Get interface from command line
if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <interface>")
    sys.exit(255)

intf = sys.argv[1]

# Read vendor and device IDs
try:
    with open(f"/sys/class/net/{intf}/device/vendor") as f:
        vdr_id = f.read().strip()
    with open(f"/sys/class/net/{intf}/device/device") as f:
        dev_id = f.read().strip()
except IOError:
    print("Can't read interface data.")
    sys.exit(2)

# Validate device
if vdr_id != '0x8086' or dev_id not in ('0x10fb', '0x154d'):
    print("Not a recognized Intel x520 card.")
    sys.exit(3)

# Read EEPROM value
try:
    output = subprocess.check_output(['ethtool', '-e', intf, 'offset', '0x58', 'length', '1']).decode('utf-8')
except subprocess.CalledProcessError:
    print("Failed to read EEPROM.")
    sys.exit(4)

val = output.strip().split('\n')[-1].split()[-1]
val_bin = int(val, 16)

print(f"EEPROM Value at 0x58 is 0x{val} ({bin(val_bin)})")

if val_bin & 0b00000001:
    print("Card is already unlocked for all SFP modules. Nothing to do.")
    sys.exit(0)
else:
    print("Card is locked to Intel-only SFP modules. Patching EEPROM...")
    new_val = val_bin | 0b00000001
    print(f"New EEPROM Value at 0x58 will be {hex(new_val)} ({bin(new_val)})")

    magic = f"{dev_id}{vdr_id[2:]}"
    cmd = [
        'sudo', 'ethtool', '-E', intf,
        'magic', magic,
        'offset', '0x58',
        'value', hex(new_val),
        'length', '1'
    ]
    print(f"Running: {' '.join(cmd)}")
    run_command(cmd)

    print("Reboot the machine for changes to take effect.")
