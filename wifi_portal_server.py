"""
WiFi Portal Server

Flask-based captive portal for WiFi configuration during AP provisioning mode.
Runs on port 80 when the device is broadcasting as an access point.
"""

from flask import Flask, request, jsonify, render_template, redirect
import subprocess
import json


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
            subprocess.run(
                ["sudo", "nmcli", "device", "wifi", "rescan"],
                capture_output=True,
                timeout=10
            )
            
            # Wait a moment for scan to complete
            import time
            time.sleep(2)
            
            # Get the list of available networks
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            networks = []
            seen_ssids = set()
            
            if result.returncode == 0:
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
            result = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            saved_networks = []
            
            if result.returncode == 0:
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
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                # Wait for NetworkManager to fully persist the connection
                # before returning success. This prevents race conditions
                # where the frontend requests saved networks before it's visible.
                import time
                max_wait = 5  # seconds
                poll_interval = 0.2  # seconds
                waited = 0
                connection_visible = False
                
                while waited < max_wait:
                    check_result = subprocess.run(
                        ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if check_result.returncode == 0:
                        for line in check_result.stdout.strip().split('\n'):
                            parts = line.split(':')
                            if len(parts) >= 2 and parts[0] == ssid and parts[1] == "802-11-wireless":
                                connection_visible = True
                                break
                    if connection_visible:
                        break
                    time.sleep(poll_interval)
                    waited += poll_interval
                
                return jsonify({
                    "success": True, 
                    "message": f"Network '{ssid}' saved. Stop broadcasting to connect."
                })
            else:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Failed to save network"
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
            
            result = subprocess.run(
                ["sudo", "nmcli", "connection", "delete", name],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return jsonify({"success": True, "message": f"Network '{name}' deleted."})
            else:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Failed to delete network"
                return jsonify({"success": False, "error": error_msg}), 500
                
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    # Run the server
    app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False)


if __name__ == "__main__":
    start_wifi_portal_server()
