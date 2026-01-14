"""System-level operations used by the UI."""

import json
import logging
import socket

from services.system_actions import run_command


logger = logging.getLogger(__name__)


class SystemService:
    """Handles system operations like WiFi checks and power actions."""

    def check_wifi_connection(self):
        """Check if WiFi is connected using NetworkManager.

        Returns:
            bool: True if connected to a WiFi network, False otherwise.
        """
        try:
            result = run_command(
                ["nmcli", "-t", "-f", "WIFI", "general"],
                timeout_s=5,
                log_label="wifi_check_enabled",
            )
            if not result.ok:
                return False

            # Check if WiFi is enabled
            if "enabled" not in result.stdout.lower():
                return False

            # Check actual connection status
            conn_result = run_command(
                ["nmcli", "-t", "-f", "TYPE,STATE", "device"],
                timeout_s=5,
                log_label="wifi_check_connection",
            )
            if conn_result.ok:
                for line in conn_result.stdout.strip().split("\n"):
                    if line.startswith("wifi:") and ":connected" in line.lower():
                        return True
            return False
        except Exception:
            logger.exception("WiFi check failed")
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
            result = run_command(
                ["tailscale", "status", "--json"],
                timeout_s=5,
                log_label="tailscale_status",
            )
            if result.ok and result.stdout:
                status_data = json.loads(result.stdout)
                dns_name = status_data.get("Self", {}).get("DNSName", "")
                if dns_name:
                    return dns_name.rstrip(".")
            return "Not available"
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return "Not available"

    def shutdown(self):
        """Perform a system shutdown."""
        run_command(
            ["sudo", "shutdown", "now"],
            timeout_s=10,
            log_label="shutdown",
        )

    def reboot(self):
        """Perform a system reboot."""
        run_command(
            ["sudo", "shutdown", "-r", "now"],
            timeout_s=10,
            log_label="reboot",
        )

    def apply_screen_sleep_settings(self, enabled, minutes):
        """Apply screen sleep settings using xset."""
        if enabled:
            timeout_seconds = minutes * 60
            run_command(
                ["xset", "s", str(timeout_seconds)],
                timeout_s=5,
                log_label="screen_sleep_enable",
            )
        else:
            run_command(
                ["xset", "s", "off"],
                timeout_s=5,
                log_label="screen_sleep_disable",
            )
