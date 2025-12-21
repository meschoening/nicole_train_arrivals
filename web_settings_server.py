import threading
from flask import Flask, request, jsonify, render_template, redirect, url_for, Response
import config_handler
import message_handler
import os
from datetime import datetime
import subprocess
import sys
import time
import json


_data_lock = threading.Lock()
_message_trigger = {"message": None, "pending": False}
_message_trigger_lock = threading.Lock()
_settings_changed_trigger = {"pending": False}
_settings_changed_lock = threading.Lock()

# SSL certificate directory (expanded from ~)
_SSL_CERT_DIR = os.path.expanduser("~/https")

# Track SSL status for warning display
_ssl_enabled = False


def _get_ssl_cert_paths():
    """
    Auto-detect SSL certificate and key files in ~/https directory.
    Returns tuple of (cert_path, key_path) or (None, None) if not found.
    """
    cert_path = None
    key_path = None
    
    if os.path.isdir(_SSL_CERT_DIR):
        for filename in os.listdir(_SSL_CERT_DIR):
            filepath = os.path.join(_SSL_CERT_DIR, filename)
            if os.path.isfile(filepath):
                if filename.endswith('.crt') and cert_path is None:
                    cert_path = filepath
                elif filename.endswith('.key') and key_path is None:
                    key_path = filepath
    
    return cert_path, key_path


def _check_ssl_certs():
    """Check if SSL certificate files exist."""
    cert_path, key_path = _get_ssl_cert_paths()
    return cert_path is not None and key_path is not None


def get_pending_message_trigger():
    """
    Check if there's a pending message trigger from the web interface.
    Returns the message (or None for random) and clears the pending flag.
    
    Returns:
        str or None: Message to display, or None if no trigger pending or for random message
    """
    with _message_trigger_lock:
        if _message_trigger["pending"]:
            message = _message_trigger["message"]
            _message_trigger["pending"] = False
            _message_trigger["message"] = None
            return message
        return False


def get_pending_settings_change():
    """
    Check if there's a pending settings change from the web interface.
    Returns True if settings were changed and clears the pending flag.
    
    Returns:
        bool: True if settings were changed, False otherwise
    """
    with _settings_changed_lock:
        if _settings_changed_trigger["pending"]:
            _settings_changed_trigger["pending"] = False
            return True
        return False


def _ensure_lines(data_handler):
    lines = data_handler.get_cached_lines()
    if lines is None or lines.empty:
        lines = data_handler.fetch_lines()
    return lines


def _get_stations_for_line(data_handler, line_code):
    if not line_code:
        return []
    with _data_lock:
        stations_df = data_handler.get_cached_stations(line_code)
    if stations_df is None or stations_df.empty:
        return []
    return [{"name": row.get("Name", ""), "code": row.get("Code", "")} for _, row in stations_df.iterrows()]


def _get_directions_for_station(data_handler, station_code):
    if not station_code:
        return []
    with _data_lock:
        predictions_df = data_handler.get_cached_predictions(station_code)
    if predictions_df is None or predictions_df.empty:
        return []
    # Group by destination, collect unique line codes
    by_destination = {}
    for _, row in predictions_df.iterrows():
        dest = row.get("DestinationName")
        line_code = row.get("Line")
        if not dest:
            continue
        line_set = by_destination.setdefault(dest, set())
        if line_code:
            line_set.add(line_code)
    # Build sorted list of { name, lines }
    results = [
        {"name": name, "lines": sorted(list(lines))}
        for name, lines in by_destination.items()
    ]
    results.sort(key=lambda d: d["name"])  # sort alphabetically by destination name
    return results


def _get_available_timezones():
    """Get list of available timezones from timedatectl, filtered to canonical names only."""
    # Only include canonical timezone prefixes (excludes legacy names like US/Central, EST, etc.)
    canonical_prefixes = (
        "Africa/", "America/", "Antarctica/", "Arctic/", "Asia/",
        "Atlantic/", "Australia/", "Europe/", "Indian/", "Pacific/"
    )
    
    try:
        result = subprocess.run(
            ["timedatectl", "list-timezones"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            timezones = [tz.strip() for tz in result.stdout.splitlines() if tz.strip()]
            # Filter to canonical timezones + UTC
            filtered = [tz for tz in timezones if tz.startswith(canonical_prefixes) or tz == "UTC"]
            return filtered if filtered else timezones  # Fall back to full list if filter is empty
    except Exception:
        pass
    # Fallback to common timezones if timedatectl fails (e.g., on Windows dev machine)
    return [
        "America/New_York", "America/Chicago", "America/Denver",
        "America/Los_Angeles", "America/Phoenix", "America/Anchorage",
        "Pacific/Honolulu", "UTC"
    ]


def _get_current_system_timezone():
    """Get the current system timezone from timedatectl."""
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "America/Chicago"  # Fallback default


def start_web_settings_server(data_handler, host="0.0.0.0", port=443):
    global _ssl_enabled
    
    # Check for SSL certificates
    ssl_context = None
    cert_path, key_path = _get_ssl_cert_paths()
    if cert_path and key_path:
        ssl_context = (cert_path, key_path)
        _ssl_enabled = True
    else:
        _ssl_enabled = False
        port = 80  # Fall back to HTTP port
    
    app = Flask(__name__, template_folder="templates")

    def _get_config_last_saved():
        config_path = getattr(config_handler, 'CONFIG_FILE', 'config.json')
        if os.path.exists(config_path):
            mtime = os.path.getmtime(config_path)
            dt = datetime.fromtimestamp(mtime)
            return dt.strftime("%m/%d/%Y %I:%M:%S %p")
        return "Never"

    def _get_device_ip():
        import socket as _socket
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "Unable to detect"

    def _get_tailscale_address():
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                status_data = json.loads(result.stdout)
                dns_name = status_data.get("Self", {}).get("DNSName", "")
                if dns_name:
                    return dns_name.rstrip('.')
            return "Not available"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, json.JSONDecodeError, KeyError, FileNotFoundError):
            return "Not available"

    def _get_commit_version():
        """Get the latest git commit version info (short hash, message, author date)."""
        cwd = os.path.dirname(os.path.abspath(__file__))
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%h - %s (%ad)", "--date=format:%b %d, %Y %I:%M %p"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return "Not available"
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return "Not available"

    def _check_tailscale_installed():
        """Check if tailscale is installed on the system."""
        try:
            result = subprocess.run(
                ["which", "tailscale"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False

    def _get_ssl_status():
        """Get SSL certificate status including tailscale info."""
        cert_path, key_path = _get_ssl_cert_paths()
        tailscale_installed = _check_tailscale_installed()
        tailscale_hostname = ""
        
        if tailscale_installed:
            tailscale_hostname = _get_tailscale_address()
            if tailscale_hostname == "Not available":
                tailscale_hostname = ""
        
        return {
            "tailscale_installed": tailscale_installed,
            "tailscale_hostname": tailscale_hostname,
            "cert_found": cert_path is not None,
            "cert_path": cert_path or "",
            "key_found": key_path is not None,
            "key_path": key_path or "",
        }

    def _get_messages_last_saved():
        messages_path = getattr(message_handler, 'MESSAGES_FILE', 'messages.json')
        if os.path.exists(messages_path):
            mtime = os.path.getmtime(messages_path)
            dt = datetime.fromtimestamp(mtime)
            return dt.strftime("%m/%d/%Y %I:%M:%S %p")
        return "Never"

    def _get_display_name():
        """Get the display name (title_text) from config for page titles."""
        config = config_handler.load_config()
        return config.get("title_text", "Nicole's Train Tracker!")

    def _check_for_updates():
        """
        Check if git updates are available by comparing local and remote HEADs.
        Returns True if updates are available, False otherwise.
        Does NOT run git fetch - relies on fetch having been run recently (by the display app).
        """
        cwd = os.path.dirname(os.path.abspath(__file__))
        
        try:
            # Get local HEAD
            local_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if local_result.returncode != 0:
                return False
            
            local_head = local_result.stdout.strip()
            
            # Get remote HEAD (try origin/main first, then origin/master)
            remote_head = None
            for branch in ["origin/main", "origin/master"]:
                remote_result = subprocess.run(
                    ["git", "rev-parse", branch],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if remote_result.returncode == 0:
                    remote_head = remote_result.stdout.strip()
                    break
            
            if remote_head is None:
                return False
            
            return local_head != remote_head
            
        except Exception:
            return False

    @app.get("/messages")
    def get_messages():
        config = message_handler.load_messages()
        messages_list = config.get("messages", [])
        return render_template(
            "messages.html",
            config=config,
            messages_json=json.dumps(messages_list),
            last_saved=_get_messages_last_saved(),
            display_name=_get_display_name(),
        )

    @app.post("/messages")
    def post_messages():
        data = request.get_json()
        message_handler.save_messages(data)
        return jsonify({
            "status": "saved",
            "timestamp": _get_messages_last_saved()
        })

    @app.post("/api/trigger_message")
    def api_trigger_message():
        data = request.get_json() or {}
        message = data.get("message")
        
        with _message_trigger_lock:
            _message_trigger["message"] = message
            _message_trigger["pending"] = True
        
        return jsonify({"status": "triggered"})

    @app.get("/settings")
    def get_settings():
        config = config_handler.load_config()
        
        # Always get timezone from system, not config
        current_timezone = _get_current_system_timezone()
        
        with _data_lock:
            lines_df = _ensure_lines(data_handler)
        lines = []
        if lines_df is not None and not lines_df.empty:
            for _, line in lines_df.iterrows():
                lines.append({
                    "line_code": line.get("LineCode", ""),
                    "display_name": line.get("DisplayName", "")
                })

        selected_line = config.get("selected_line")
        stations = _get_stations_for_line(data_handler, selected_line)
        selected_station = config.get("selected_station")
        directions = _get_directions_for_station(data_handler, selected_station)

        return render_template(
            "settings.html",
            config=config,
            lines=lines,
            stations=stations,
            directions=directions,
            timezones=_get_available_timezones(),
            current_timezone=current_timezone,
            last_saved=_get_config_last_saved(),
            display_name=_get_display_name(),
        )

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            device_ip=_get_device_ip(),
            tailscale_address=_get_tailscale_address(),
            commit_version=_get_commit_version(),
            ssl_enabled=_ssl_enabled,
            display_name=_get_display_name(),
            update_available=_check_for_updates()
        )

    @app.get("/update")
    def get_update():
        config = config_handler.load_config()
        return render_template(
            "update.html",
            display_name=_get_display_name(),
            update_check_interval=config.get("update_check_interval_seconds", 60),
            last_saved=_get_config_last_saved()
        )

    @app.get("/api-key")
    def get_api_key():
        config = config_handler.load_config()
        # Check SSH key status for initial page render
        home = os.path.expanduser("~")
        ssh_private = os.path.join(home, ".ssh", "id_ed25519")
        ssh_public = os.path.join(home, ".ssh", "id_ed25519.pub")
        ssh_key_exists = os.path.exists(ssh_private) and os.path.exists(ssh_public)
        ssh_public_key = ""
        if ssh_key_exists:
            try:
                with open(ssh_public, "r") as f:
                    ssh_public_key = f.read().strip()
            except Exception:
                pass
        # Get git remote type for initial page render
        git_remote_info = _get_git_remote_info()
        git_remote_type = git_remote_info["type"]
        # Get SSL status for initial page render
        ssl_status = _get_ssl_status()
        return render_template(
            "api_key.html",
            api_key=config.get("api_key", ""),
            last_saved=_get_config_last_saved(),
            ssh_key_exists=ssh_key_exists,
            ssh_public_key=ssh_public_key,
            git_remote_type=git_remote_type,
            display_name=_get_display_name(),
            ssl_status=ssl_status,
        )

    @app.post("/api-key")
    def post_api_key():
        api_key = request.form.get("api_key", "")
        config_handler.save_config("api_key", api_key)
        return redirect(url_for("index"))

    def _get_ssh_key_paths():
        """Get the paths to SSH key files, dynamically detecting home directory."""
        home = os.path.expanduser("~")
        ssh_dir = os.path.join(home, ".ssh")
        private_key = os.path.join(ssh_dir, "id_ed25519")
        public_key = os.path.join(ssh_dir, "id_ed25519.pub")
        return ssh_dir, private_key, public_key

    def _check_ssh_keys_exist():
        """Check if SSH keys exist and return public key content if they do."""
        _, private_key, public_key = _get_ssh_key_paths()
        if os.path.exists(private_key) and os.path.exists(public_key):
            try:
                with open(public_key, "r") as f:
                    return True, f.read().strip()
            except Exception:
                return True, ""
        return False, ""

    @app.get("/api/ssh-key-status")
    def api_ssh_key_status():
        exists, public_key = _check_ssh_keys_exist()
        return jsonify({
            "exists": exists,
            "public_key": public_key if exists else ""
        })

    @app.post("/api/generate-ssh-key")
    def api_generate_ssh_key():
        data = request.get_json() or {}
        email = data.get("email", "").strip()
        
        # Sanitize email to prevent command injection
        # Only allow alphanumeric, @, ., -, _, +
        import re
        if not email or not re.match(r'^[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({"success": False, "error": "Invalid email address format"}), 400
        
        ssh_dir, private_key, public_key = _get_ssh_key_paths()
        
        # Check if keys already exist
        if os.path.exists(private_key) or os.path.exists(public_key):
            return jsonify({"success": False, "error": "SSH keys already exist"}), 400
        
        try:
            # Ensure .ssh directory exists with proper permissions
            if not os.path.exists(ssh_dir):
                os.makedirs(ssh_dir, mode=0o700)
            
            # Generate SSH key with no passphrase
            result = subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-C", email, "-N", "", "-f", private_key],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                return jsonify({"success": False, "error": error_msg}), 500
            
            # Read and return the public key
            if os.path.exists(public_key):
                with open(public_key, "r") as f:
                    pub_key_content = f.read().strip()
                # Convert git remote to SSH if it was HTTPS
                convert_result = _convert_git_remote_to_ssh()
                return jsonify({
                    "success": True,
                    "public_key": pub_key_content,
                    "remote_type": convert_result["type"],
                    "remote_converted": convert_result.get("converted", False)
                })
            else:
                return jsonify({"success": False, "error": "Key generation succeeded but public key file not found"}), 500
                
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.post("/api/regenerate-ssh-key")
    def api_regenerate_ssh_key():
        """Delete existing SSH keys and generate new ones."""
        data = request.get_json() or {}
        email = data.get("email", "").strip()
        
        # Sanitize email to prevent command injection
        import re
        if not email or not re.match(r'^[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({"success": False, "error": "Invalid email address format"}), 400
        
        ssh_dir, private_key, public_key = _get_ssh_key_paths()
        
        # Check if keys exist - we need them to exist to regenerate
        if not os.path.exists(private_key) and not os.path.exists(public_key):
            return jsonify({"success": False, "error": "No existing SSH keys to regenerate"}), 400
        
        try:
            # Delete existing keys
            if os.path.exists(private_key):
                os.remove(private_key)
            if os.path.exists(public_key):
                os.remove(public_key)
            
            # Generate new SSH key with no passphrase
            result = subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-C", email, "-N", "", "-f", private_key],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                return jsonify({"success": False, "error": error_msg}), 500
            
            # Read and return the new public key
            if os.path.exists(public_key):
                with open(public_key, "r") as f:
                    pub_key_content = f.read().strip()
                # Convert git remote to SSH if it was HTTPS
                convert_result = _convert_git_remote_to_ssh()
                return jsonify({
                    "success": True,
                    "public_key": pub_key_content,
                    "remote_type": convert_result["type"],
                    "remote_converted": convert_result.get("converted", False)
                })
            else:
                return jsonify({"success": False, "error": "Key generation succeeded but public key file not found"}), 500
                
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    def _get_git_remote_info():
        """Get git remote origin URL and determine if it's HTTPS or SSH."""
        cwd = os.path.dirname(os.path.abspath(__file__))
        try:
            result = subprocess.run(
                ["sudo", "-u", "max", "git", "remote", "-v"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0 and result.stdout:
                # Parse first line (origin fetch URL)
                for line in result.stdout.splitlines():
                    if "origin" in line and "(fetch)" in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            url = parts[1]
                            if url.startswith("https://"):
                                return {"type": "https", "url": url}
                            elif url.startswith("git@") or url.startswith("ssh://"):
                                return {"type": "ssh", "url": url}
                            else:
                                return {"type": "unknown", "url": url}
        except Exception:
            pass
        return {"type": "unknown", "url": ""}

    def _convert_git_remote_to_ssh():
        """Convert HTTPS remote URL to SSH format for GitHub."""
        remote_info = _get_git_remote_info()
        if remote_info["type"] != "https":
            return {"converted": False, "type": remote_info["type"]}
        
        url = remote_info["url"]
        # Parse GitHub HTTPS URL: https://github.com/user/repo.git
        import re
        match = re.match(r'https://github\.com/([^/]+)/(.+?)(?:\.git)?$', url)
        if not match:
            return {"converted": False, "type": "https", "error": "Could not parse GitHub URL"}
        
        user, repo = match.groups()
        # Ensure .git suffix
        if not repo.endswith('.git'):
            repo = repo + '.git'
        ssh_url = f"git@github.com:{user}/{repo}"
        
        cwd = os.path.dirname(os.path.abspath(__file__))
        try:
            result = subprocess.run(
                ["sudo", "-u", "max", "git", "remote", "set-url", "origin", ssh_url],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return {"converted": True, "type": "ssh", "new_url": ssh_url}
            else:
                return {"converted": False, "type": "https", "error": result.stderr.strip()}
        except Exception as e:
            return {"converted": False, "type": "https", "error": str(e)}

    @app.get("/api/git-remote-status")
    def api_git_remote_status():
        """Get current git remote type (https or ssh)."""
        info = _get_git_remote_info()
        return jsonify({"type": info["type"]})

    @app.get("/api/ssl-status")
    def api_ssl_status():
        """Get SSL certificate status."""
        return jsonify(_get_ssl_status())

    @app.post("/api/generate-ssl-cert")
    def api_generate_ssl_cert():
        """Generate or regenerate SSL certificates using tailscale cert."""
        import shutil
        
        # Check if tailscale is installed
        if not _check_tailscale_installed():
            return jsonify({"success": False, "error": "Tailscale is not installed"}), 400
        
        # Get tailscale hostname
        hostname = _get_tailscale_address()
        if hostname == "Not available" or not hostname:
            return jsonify({"success": False, "error": "Could not determine Tailscale hostname"}), 400
        
        try:
            # Ensure ~/https directory exists
            if not os.path.isdir(_SSL_CERT_DIR):
                os.makedirs(_SSL_CERT_DIR, mode=0o755)
            else:
                # Clear existing contents of ~/https directory
                for filename in os.listdir(_SSL_CERT_DIR):
                    filepath = os.path.join(_SSL_CERT_DIR, filename)
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                    elif os.path.isdir(filepath):
                        shutil.rmtree(filepath)
            
            # Define output paths
            cert_file = os.path.join(_SSL_CERT_DIR, f"{hostname}.crt")
            key_file = os.path.join(_SSL_CERT_DIR, f"{hostname}.key")
            
            # Generate certificates using tailscale cert
            result = subprocess.run(
                ["sudo", "tailscale", "cert", "--cert-file", cert_file, "--key-file", key_file, hostname],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                return jsonify({"success": False, "error": error_msg}), 500
            
            # Verify files were created and change ownership to current user
            if os.path.exists(cert_file) and os.path.exists(key_file):
                # Change ownership of generated files to current user
                import pwd
                current_user = pwd.getpwuid(os.getuid()).pw_name
                subprocess.run(
                    ["sudo", "chown", current_user, cert_file, key_file],
                    capture_output=True,
                    timeout=10
                )
                return jsonify({
                    "success": True,
                    "cert_path": cert_file,
                    "key_path": key_file,
                    "message": "SSL certificates generated successfully. Restart the application to use HTTPS."
                })
            else:
                return jsonify({"success": False, "error": "Certificate generation succeeded but files not found"}), 500
                
        except subprocess.TimeoutExpired:
            return jsonify({"success": False, "error": "Certificate generation timed out"}), 500
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    def _has_git_error(output_text):
        if not output_text:
            return False
        lower = output_text.lower()
        for token in ("error:", "fatal:", "could not", "failed to", "permission denied", "cannot"):
            if token in lower:
                return True
        return False

    def _has_updates(output_text):
        if not output_text:
            return False
        lower = output_text.lower()
        if "already up to date" in lower or "already up-to-date" in lower:
            return False
        for token in ("updating", "fast-forward", "files changed", "file changed", "insertions", "deletions"):
            if token in lower:
                return True
        # Heuristic: if we have some substantial lines and no error keywords
        if "error" not in lower and "fatal" not in lower:
            lines = [ln.strip() for ln in output_text.split('\n') if ln.strip()]
            substantial = [ln for ln in lines if not ln.startswith('From') and not ln.startswith('remote:')]
            if len(substantial) > 1:
                return True
        return False

    @app.get("/api/update/run")
    def api_update_run():
        def generate():
            cwd = os.path.dirname(os.path.abspath(__file__))
            # Run `git pull` as user 'max' to avoid ownership issues
            # Use sudo -u max to run git commands under the max user
            process = subprocess.Popen(
                ["sudo", "-u", "max", "git", "pull"],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            all_output_lines = []
            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        # Stream each line to the client
                        safe = line.rstrip('\n')
                        all_output_lines.append(safe)
                        yield f"data: {safe}\n\n"
            finally:
                exit_code = process.wait()
                combined_output = "\n".join(all_output_lines)
                has_updates = _has_updates(combined_output)
                done_payload = {
                    "exit_code": exit_code,
                    "has_error": _has_git_error(combined_output) or (exit_code != 0),
                    "has_updates": has_updates,
                }
                # If update succeeded with changes, get the latest commit message
                if has_updates and not done_payload["has_error"]:
                    try:
                        commit_result = subprocess.run(
                            ["sudo", "-u", "max", "git", "log", "-1", "--format=%s"],
                            cwd=cwd,
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if commit_result.returncode == 0 and commit_result.stdout.strip():
                            done_payload["commit_message"] = commit_result.stdout.strip()
                    except Exception:
                        pass
                yield "event: done\n"
                yield f"data: {json.dumps(done_payload)}\n\n"

        headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # for some proxies
        }
        return Response(generate(), mimetype="text/event-stream", headers=headers)

    @app.post("/api/update-check-interval")
    def api_update_check_interval():
        """Save the background update check interval setting."""
        data = request.get_json() or {}
        interval = data.get("interval")
        
        # Validate interval (min 5 seconds, max 3600 seconds)
        try:
            interval = int(interval)
            if interval < 5:
                interval = 5
            elif interval > 3600:
                interval = 3600
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid interval value"}), 400
        
        config_handler.save_config("update_check_interval_seconds", interval)
        return jsonify({"success": True, "interval": interval})

    @app.get("/api/check-for-updates")
    def api_check_for_updates():
        """
        Check if updates are available by running git fetch and comparing commits.
        Non-destructive - only checks, does not apply updates.
        """
        cwd = os.path.dirname(os.path.abspath(__file__))
        
        try:
            # Run git fetch to get latest remote state
            fetch_result = subprocess.run(
                ["sudo", "-u", "max", "git", "fetch"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if fetch_result.returncode != 0:
                return jsonify({
                    "updates_available": False,
                    "error": "Failed to fetch from remote"
                })
            
            # Get local HEAD commit
            local_result = subprocess.run(
                ["sudo", "-u", "max", "git", "rev-parse", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if local_result.returncode != 0:
                return jsonify({
                    "updates_available": False,
                    "error": "Failed to get local HEAD"
                })
            
            local_head = local_result.stdout.strip()
            
            # Get remote HEAD commit (try origin/main first, then origin/master)
            remote_head = None
            for branch in ["origin/main", "origin/master"]:
                remote_result = subprocess.run(
                    ["sudo", "-u", "max", "git", "rev-parse", branch],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if remote_result.returncode == 0:
                    remote_head = remote_result.stdout.strip()
                    break
            
            if remote_head is None:
                return jsonify({
                    "updates_available": False,
                    "error": "Could not determine remote branch"
                })
            
            updates_available = local_head != remote_head
            
            return jsonify({
                "updates_available": updates_available,
                "local_commit": local_head[:8],
                "remote_commit": remote_head[:8]
            })
            
        except subprocess.TimeoutExpired:
            return jsonify({
                "updates_available": False,
                "error": "Git command timed out"
            })
        except Exception as e:
            return jsonify({
                "updates_available": False,
                "error": str(e)
            })

    @app.post("/api/restart")
    def api_restart():
        # Alias for /api/reboot - kept for backward compatibility but redirects to reboot logic
        def _do_reboot():
            try:
                time.sleep(0.25)
                os.system("sudo shutdown -r now")
            except Exception:
                raise

        threading.Thread(target=_do_reboot, daemon=True).start()
        return jsonify({"status": "rebooting"})

    @app.get("/system-management")
    def get_system_management():
        config = config_handler.load_config()
        return render_template("system_management.html", config=config, display_name=_get_display_name())

    @app.post("/api/reboot")
    def api_reboot():
        # Execute reboot command matching main_display.py implementation
        def _do_reboot():
            try:
                time.sleep(0.25)
                os.system("sudo shutdown -r now")
            except Exception:
                raise

        threading.Thread(target=_do_reboot, daemon=True).start()
        return jsonify({"status": "rebooting"})

    @app.post("/api/shutdown")
    def api_shutdown():
        # Execute shutdown command matching main_display.py implementation
        def _do_shutdown():
            try:
                time.sleep(0.25)
                os.system("sudo shutdown now")
            except Exception:
                raise

        threading.Thread(target=_do_shutdown, daemon=True).start()
        return jsonify({"status": "shutting down"})

    @app.get("/api/reboot-config")
    def api_get_reboot_config():
        config = config_handler.load_config()
        return jsonify({
            "reboot_enabled": config.get("reboot_enabled", False),
            "reboot_time": config.get("reboot_time", "12:00 AM")
        })

    @app.post("/api/reboot-config")
    def api_post_reboot_config():
        data = request.get_json()
        
        # Update reboot_enabled
        if "reboot_enabled" in data:
            config_handler.save_config("reboot_enabled", bool(data["reboot_enabled"]))
        
        # Update reboot_time from three components
        if "reboot_hour" in data and "reboot_minute" in data and "reboot_ampm" in data:
            hour = data["reboot_hour"]
            minute = data["reboot_minute"]
            ampm = data["reboot_ampm"]
            time_str = f"{hour}:{minute} {ampm}"
            config_handler.save_config("reboot_time", time_str)
        
        return jsonify({"status": "saved"})

    @app.post("/settings")
    def post_settings():
        form = request.form

        def as_bool(name):
            return form.get(name) in ("true", "True", "1", "on", "yes")

        # Update simple flags
        config_handler.save_config("show_countdown", as_bool("show_countdown"))
        config_handler.save_config("show_clock", as_bool("show_clock"))
        config_handler.save_config("filter_by_direction", as_bool("filter_by_direction"))
        config_handler.save_config("filter_by_destination_direction", as_bool("filter_by_destination_direction"))
        config_handler.save_config("reboot_enabled", as_bool("reboot_enabled"))
        config_handler.save_config("screen_sleep_enabled", as_bool("screen_sleep_enabled"))

        # Update numeric values
        minutes = form.get("screen_sleep_minutes")
        try:
            minutes_val = int(minutes) if minutes is not None else None
        except ValueError:
            minutes_val = None
        if minutes_val is not None:
            config_handler.save_config("screen_sleep_minutes", minutes_val)

        # Update refresh rate
        refresh_rate = form.get("refresh_rate_seconds")
        try:
            refresh_rate_val = int(refresh_rate) if refresh_rate is not None else None
        except ValueError:
            refresh_rate_val = None
        if refresh_rate_val is not None:
            # Validate range (5-120 seconds)
            if 5 <= refresh_rate_val <= 120:
                config_handler.save_config("refresh_rate_seconds", refresh_rate_val)

        # Update selections
        selected_line = form.get("selected_line")
        if selected_line is not None:
            config_handler.save_config("selected_line", selected_line)

        selected_station = form.get("selected_station")
        if selected_station is not None:
            config_handler.save_config("selected_station", selected_station)

        selected_destination = form.get("selected_destination")
        if selected_destination is not None:
            config_handler.save_config("selected_destination", selected_destination)

        # Update title text
        title_text = form.get("title_text")
        if title_text is not None:
            config_handler.save_config("title_text", title_text)

        # Handle timezone setting (system-only, not saved to config)
        timezone = form.get("timezone")
        if timezone:
            # Apply timezone system-wide via timedatectl
            try:
                result = subprocess.run(
                    ["sudo", "timedatectl", "set-timezone", timezone],
                    capture_output=True,
                    timeout=10
                )
                # Refresh Python's timezone cache after setting system timezone
                if result.returncode == 0:
                    time.tzset()
            except Exception:
                pass

        # Reboot time from three components
        reboot_hour = form.get("reboot_hour")
        reboot_minute = form.get("reboot_minute")
        reboot_ampm = form.get("reboot_ampm")
        if reboot_hour and reboot_minute and reboot_ampm:
            time_str = f"{reboot_hour}:{reboot_minute} {reboot_ampm}"
            config_handler.save_config("reboot_time", time_str)

        # Trigger settings changed flag for main display to refresh
        with _settings_changed_lock:
            _settings_changed_trigger["pending"] = True

        return redirect(url_for("get_settings"))

    @app.get("/api/stations")
    def api_stations():
        line_code = request.args.get("line")
        stations = _get_stations_for_line(data_handler, line_code)
        return jsonify(stations)

    @app.get("/api/directions")
    def api_directions():
        station_code = request.args.get("station")
        directions = _get_directions_for_station(data_handler, station_code)
        return jsonify(directions)

    def _run():
        app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False, ssl_context=ssl_context)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    
    # If SSL is enabled, start a redirect server on port 80 to redirect HTTP -> HTTPS
    if _ssl_enabled:
        redirect_app = Flask(__name__ + "_redirect")
        
        @redirect_app.before_request
        def redirect_to_https():
            # Redirect all HTTP requests to HTTPS
            return redirect(request.url.replace("http://", "https://", 1), code=301)
        
        def _run_redirect():
            redirect_app.run(host=host, port=80, threaded=True, use_reloader=False, debug=False)
        
        redirect_thread = threading.Thread(target=_run_redirect, daemon=True)
        redirect_thread.start()
    
    return thread


