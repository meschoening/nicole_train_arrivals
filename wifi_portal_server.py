"""
WiFi Portal Server

Flask-based captive portal for WiFi configuration during AP provisioning mode.
Runs on port 80 when the device is broadcasting as an access point.
"""

from flask import Flask, request, jsonify, render_template, redirect
import json
from services.system_actions import run_command


def start_wifi_portal_server(host="0.0.0.0", port=80):
    """Start the WiFi configuration portal server."""
    
    app = Flask(__name__, template_folder="templates")
    
    @app.route("/")
    def index():
        """Main WiFi configuration page."""
        return render_template("wifi_setup.html")
    
    @app.route("/api/scan")
    def api_scan():
        """Scan for available WiFi networks."""
        try:
            # Use nmcli to scan for networks
            # First, trigger a rescan
            run_command(
                ["sudo", "nmcli", "device", "wifi", "rescan"],
                timeout_s=10,
                log_label="portal_wifi_rescan",
            )
            
            # Wait a moment for scan to complete
            import time
            time.sleep(2)
            
            # Get the list of available networks
            result = run_command(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
                timeout_s=10,
                log_label="portal_wifi_list",
            )
            
            networks = []
            seen_ssids = set()
            
            if result.ok:
                for line in result.stdout.strip().split('\n'):
                    if not line.strip():
                        continue
                    parts = line.split(':')
                    if len(parts) >= 3:
                        ssid = parts[0]
                        # Skip empty SSIDs and duplicates
                        if ssid and ssid not in seen_ssids:
                            seen_ssids.add(ssid)
                            networks.append({
                                "ssid": ssid,
                                "signal": parts[1] if len(parts) > 1 else "",
                                "security": parts[2] if len(parts) > 2 else ""
                            })
            
            # Sort by signal strength (descending)
            networks.sort(key=lambda x: int(x["signal"]) if x["signal"].isdigit() else 0, reverse=True)
            
            return jsonify({"success": True, "networks": networks})
            
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route("/api/saved")
    def api_saved():
        """List saved WiFi network configurations."""
        try:
            result = run_command(
                ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
                timeout_s=10,
                log_label="portal_saved_networks",
            )
            
            saved_networks = []
            
            if result.ok:
                for line in result.stdout.strip().split('\n'):
                    if not line.strip():
                        continue
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[1] == "802-11-wireless":
                        saved_networks.append({"name": parts[0]})
            
            return jsonify({"success": True, "networks": saved_networks})
            
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route("/api/connect", methods=["POST"])
    def api_connect():
        """Save WiFi credentials and optionally connect."""
        try:
            data = request.get_json() or {}
            ssid = data.get("ssid", "").strip()
            password = data.get("password", "").strip()
            
            if not ssid:
                return jsonify({"success": False, "error": "SSID is required"}), 400
            
            # Add new connection using nmcli
            # This will save the connection for later use
            cmd = [
                "sudo", "nmcli", "connection", "add",
                "type", "wifi",
                "con-name", ssid,
                "ssid", ssid
            ]
            
            if password:
                cmd.extend([
                    "wifi-sec.key-mgmt", "wpa-psk",
                    "wifi-sec.psk", password
                ])
            
            result = run_command(
                cmd,
                timeout_s=15,
                log_label="portal_connect",
            )
            
            if result.ok:
                # Wait for NetworkManager to fully persist the connection
                # before returning success. This prevents race conditions
                # where the frontend requests saved networks before it's visible.
                import time
                max_wait = 2  # seconds
                poll_interval = 0.2  # seconds
                waited = 0
                connection_visible = False
                
                while waited < max_wait:
                    try:
                        check_result = run_command(
                            ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
                            timeout_s=2,
                            log_label="portal_connect_poll",
                        )
                        if check_result.ok:
                            for line in check_result.stdout.strip().split('\n'):
                                parts = line.split(':')
                                if len(parts) >= 2 and parts[0] == ssid and parts[1] == "802-11-wireless":
                                    connection_visible = True
                                    break
                    except Exception:
                        pass  # Ignore errors during polling, just retry
                    
                    if connection_visible:
                        break
                    time.sleep(poll_interval)
                    waited += poll_interval
                
                return jsonify({
                    "success": True, 
                    "message": f"Network '{ssid}' saved. Stop broadcasting to connect."
                })
            else:
                error_msg = result.stderr.strip() or result.stdout.strip() or result.error or "Failed to save network"
                return jsonify({"success": False, "error": error_msg}), 500
                
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route("/api/delete", methods=["POST"])
    def api_delete():
        """Delete a saved WiFi connection."""
        try:
            data = request.get_json() or {}
            name = data.get("name", "").strip()
            
            if not name:
                return jsonify({"success": False, "error": "Connection name is required"}), 400
            
            result = run_command(
                ["sudo", "nmcli", "connection", "delete", name],
                timeout_s=10,
                log_label="portal_delete_network",
            )
            
            if result.ok:
                return jsonify({"success": True, "message": f"Network '{name}' deleted."})
            else:
                error_msg = result.stderr.strip() or result.stdout.strip() or result.error or "Failed to delete network"
                return jsonify({"success": False, "error": error_msg}), 500
                
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    # Run the server
    app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False)


if __name__ == "__main__":
    start_wifi_portal_server()
