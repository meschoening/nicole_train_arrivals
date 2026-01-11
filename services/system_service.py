"""System-level operations used by the UI."""

import json
import os
import socket
import subprocess


class SystemService:
    """Handles system operations like WiFi checks and power actions."""

    def check_wifi_connection(self):
        """Check if WiFi is connected using NetworkManager.

        Returns:
            bool: True if connected to a WiFi network, False otherwise.
        """
        try:
            print("[WiFi Check] Running: nmcli -t -f WIFI general")
            result = subprocess.run(
                ["nmcli", "-t", "-f", "WIFI", "general"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"[WiFi Check] Return code: {result.returncode}")
            print(f"[WiFi Check] stdout: {result.stdout.strip()}")
            print(f"[WiFi Check] stderr: {result.stderr.strip()}")

            if result.returncode != 0:
                print("[WiFi Check] Command failed, returning False")
                return False

            # Check if WiFi is enabled
            if "enabled" not in result.stdout.lower():
                print("[WiFi Check] WiFi not enabled in output, returning False")
                return False

            print("[WiFi Check] WiFi is enabled, checking connection status...")
            print("[WiFi Check] Running: nmcli -t -f TYPE,STATE device")

            # Check actual connection status
            conn_result = subprocess.run(
                ["nmcli", "-t", "-f", "TYPE,STATE", "device"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"[WiFi Check] Return code: {conn_result.returncode}")
            print(f"[WiFi Check] stdout: {conn_result.stdout.strip()}")
            print(f"[WiFi Check] stderr: {conn_result.stderr.strip()}")

            if conn_result.returncode == 0:
                for line in conn_result.stdout.strip().split("\n"):
                    print(f"[WiFi Check] Checking line: {line}")
                    if line.startswith("wifi:") and ":connected" in line.lower():
                        print("[WiFi Check] Found connected WiFi! Returning True")
                        return True
            print("[WiFi Check] No connected WiFi found, returning False")
            return False
        except Exception as e:
            print(f"[WiFi Check] Exception: {e}")
            return False

    def get_device_ip(self):
        """Get the local IP address of the device."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
            s.close()
            return ip_address
        except Exception:
            return "Unable to detect"

    def get_tailscale_address(self):
        """Get the Tailscale address of the device."""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                status_data = json.loads(result.stdout)
                dns_name = status_data.get("Self", {}).get("DNSName", "")
                if dns_name:
                    return dns_name.rstrip(".")
            return "Not available"
        except (
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            KeyError,
            FileNotFoundError,
        ):
            return "Not available"

    def shutdown(self):
        """Perform a system shutdown."""
        os.system("sudo shutdown now")

    def reboot(self):
        """Perform a system reboot."""
        os.system("sudo shutdown -r now")

    def apply_screen_sleep_settings(self, enabled, minutes):
        """Apply screen sleep settings using xset."""
        if enabled:
            timeout_seconds = minutes * 60
            os.system(f"xset s {timeout_seconds}")
        else:
            os.system("xset s off")
