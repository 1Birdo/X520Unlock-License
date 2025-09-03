import os
import subprocess
import sys
import binascii
import hashlib
import hmac

def run_command(cmd_list):
    """Execute a command and return its output"""
    try:
        if isinstance(cmd_list, str):
            result = subprocess.run(cmd_list, shell=True, check=True, 
                                  capture_output=True, text=True)
        else:
            result = subprocess.run(cmd_list, check=True, 
                                  capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e.cmd if isinstance(e.cmd, str) else ' '.join(e.cmd)}")
        print(f"Error: {e.stderr}")
        sys.exit(1)

def main():
    intf = 'enp101s0f0'
    
    # Reload ixgbe driver with unsupported SFP support
    run_command(['sudo', 'modprobe', '-r', 'ixgbe'])
    run_command(['sudo', 'modprobe', 'ixgbe', 'allow_unsupported_sfp=1'])

    # Verify Intel x520 card
    try:
        with open(f"/sys/class/net/{intf}/device/vendor") as f:
            vdr_id = f.read().strip()
        with open(f"/sys/class/net/{intf}/device/device") as f:
            dev_id = f.read().strip()
    except IOError:
        print("Can't read interface data.")
        sys.exit(2)

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

    # Patch EEPROM if needed
    if val_bin & 0b00000001:
        print("Card is already unlocked for all SFP modules. Nothing to do.")
    else:
        print("Card is locked to Intel-only SFP modules. Patching EEPROM...")
        new_val = val_bin | 0b00000001
        print(f"New EEPROM Value at 0x58 will be {hex(new_val)} ({bin(new_val)})")

        magic = f"{dev_id}{vdr_id[2:]}"
        cmd = [
            'sudo', 'ethtool', '-E', intf,
            'magic', magic,
            'offset', '0x58',
            'value', hex(new_val)
        ]
        run_command(cmd)
        print("EEPROM patched successfully. Reboot for changes to take effect.")

    # Get MAC address and generate license key
    try:
        mac_output = run_command("sudo /home/sf/nfs/ipmicfg -m")
        mac_line = next((line for line in mac_output.splitlines() if "MAC=" in line), None)
        if not mac_line:
            raise ValueError("MAC address not found")
        macaddr = mac_line.replace("MAC=", "").strip().replace(':', '')
        
        mac_bytes = binascii.unhexlify(macaddr)
        hex_key = bytes.fromhex("8544E3B47ECA58F9583043F8")
        digest = hmac.new(hex_key, mac_bytes, hashlib.sha1).hexdigest()[:24]
        lkey = '-'.join([digest[i:i+4] for i in range(0, 24, 4)])

        # Activate product key
        run_command(['sudo', '/home/sf/nfs/sum/sum', '-c', 'ActivateProductKey', '--key', lkey])
        
        # Apply BIOS configuration
        #run_command(['sudo', '/home/sf/nfs/sum/sum', '--file', '/home/sf/nfs/sum/cbios5.cfg', '--preserve_setting'])
        run_command(['sudo', '/home/sf/nfs/sum/sum', '--file', '/home/sf/nfs/sum/cbios5.cfg', '-c', 'ChangeBiosCfg'])

        print(f"License key activated: {lkey}")
        
    except Exception as e:
        print(f"Error during license activation: {e}")
        sys.exit(5)

if __name__ == "__main__":
    main()