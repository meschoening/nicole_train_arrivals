import threading
from flask import Flask, request, jsonify, render_template, redirect, url_for, Response
from subprocess import PIPE, STDOUT
from services.background_jobs import background_jobs
from services.config_store import ConfigStore
from services.message_store import MessageStore
from services.system_service import SystemService
from services.update_service import UpdateServiceRunner, has_git_error, has_updates
from services.system_actions import run_command, start_process
import os
from datetime import datetime, timedelta
import sys
import time
import json
import traceback

# Debug logging for git operations
_GIT_DEBUG = True

def _git_debug_log(message, include_stack=False):
    """Log git operation debug info with timestamp."""
    if _GIT_DEBUG:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        flag_state = background_jobs.is_git_operation_in_progress()
        print(f"[GIT-DEBUG {timestamp}] [web_server] [flag={flag_state}] {message}", flush=True)
        if include_stack:
            print(f"[GIT-DEBUG {timestamp}] Stack trace:", flush=True)
            traceback.print_stack()


_data_lock = threading.Lock()


def is_git_operation_in_progress():
    """Check if a git operation is currently in progress."""
    result = background_jobs.is_git_operation_in_progress()
    if _GIT_DEBUG:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"[GIT-DEBUG {timestamp}] [web_server] is_git_operation_in_progress() -> {result}", flush=True)
    return result


def set_git_operation_in_progress(active, caller="unknown"):
    """Set the git operation in progress flag."""
    if _GIT_DEBUG:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"[GIT-DEBUG {timestamp}] [web_server] set_git_operation_in_progress({active}) called by {caller}", flush=True)
    background_jobs.set_git_operation_in_progress(active, caller=caller)

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
    return background_jobs.consume_message_trigger()


def get_pending_settings_change():
    """
    Check if there's a pending settings change from the web interface.
    Returns True if settings were changed and clears the pending flag.
    
    Returns:
        bool: True if settings were changed, False otherwise
    """
    return background_jobs.consume_settings_changed()


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
        result = run_command(
            ["timedatectl", "list-timezones"],
            timeout_s=10,
            log_label="timezones_list",
        )
        if result.ok:
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
        result = run_command(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            timeout_s=5,
            log_label="timezone_current",
        )
        if result.ok and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "America/Chicago"  # Fallback default


def start_web_settings_server(data_handler, host="0.0.0.0", port=443):
    global _ssl_enabled

    config_store = ConfigStore()
    message_store = MessageStore()
    system_service = SystemService()
    git_user = "max"
    update_service = UpdateServiceRunner(
        working_dir=os.path.dirname(os.path.abspath(__file__)),
        git_user=git_user,
    )
    
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
        config_path = config_store.path
        if os.path.exists(config_path):
            mtime = os.path.getmtime(config_path)
            dt = datetime.fromtimestamp(mtime)
            return dt.strftime("%m/%d/%Y %I:%M:%S %p")
        return "Never"

    def _get_device_ip():
        return system_service.get_device_ip()

    def _get_tailscale_address():
        return system_service.get_tailscale_address()

    def _get_commit_version():
        """Get the latest git commit version info (short hash, message, author date)."""
        cwd = os.path.dirname(os.path.abspath(__file__))
        try:
            result = run_command(
                ["git", "log", "-1", "--format=%h - %s (%ad)", "--date=format:%b %d, %Y %I:%M %p"],
                cwd=cwd,
                timeout_s=5,
                log_label="git_latest_commit",
            )
            if result.ok and result.stdout.strip():
                return result.stdout.strip()
            return "Not available"
        except Exception:
            return "Not available"

    def _get_reboot_warning_status():
        config = config_store.load()
        reboot_enabled = config.get("reboot_enabled", False)
        reboot_time_str = config.get("reboot_time", "12:00 AM")
        now = datetime.now()
        target_epoch = None
        seconds_until_reboot = None

        if reboot_enabled:
            try:
                reboot_time = datetime.strptime(reboot_time_str, "%I:%M %p").time()
                target_dt = datetime.combine(now.date(), reboot_time)
                if target_dt <= now:
                    target_dt += timedelta(days=1)
                target_epoch = int(target_dt.timestamp())
                seconds_until_reboot = int((target_dt - now).total_seconds())
            except ValueError:
                pass

        return {
            "reboot_enabled": reboot_enabled,
            "reboot_time": reboot_time_str,
            "target_epoch": target_epoch,
            "seconds_until_reboot": seconds_until_reboot,
            "server_now_epoch": int(now.timestamp()),
        }

    def _check_tailscale_installed():
        """Check if tailscale is installed on the system."""
        try:
            result = run_command(
                ["which", "tailscale"],
                timeout_s=5,
                log_label="tailscale_check",
            )
            return result.ok
        except Exception:
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
        messages_path = message_store.path
        if os.path.exists(messages_path):
            mtime = os.path.getmtime(messages_path)
            dt = datetime.fromtimestamp(mtime)
            return dt.strftime("%m/%d/%Y %I:%M:%S %p")
        return "Never"

    def _get_display_name():
        """Get the display name (title_text) from config for page titles."""
        return config_store.get_str("title_text", "Nicole's Train Tracker!")

    def check_for_updates():
        """
        Check if git updates are available by comparing local and remote HEADs.
        Returns True if updates are available, False otherwise.
        Does NOT run git fetch - relies on fetch having been run recently (by the display app).
        Uses the configured git_branch setting to determine which branch to check.
        """
        try:
            configured_branch = config_store.get_str("git_branch", "main")
            local_head, remote_head = update_service.get_heads(timeout=5, branch=configured_branch)
            if not local_head or not remote_head:
                return False
            return local_head != remote_head
        except Exception:
            return False

    @app.get("/messages")
    def get_messages():
        config = message_store.load()
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
        message_store.save(data)
        return jsonify({
            "status": "saved",
            "timestamp": _get_messages_last_saved()
        })

    @app.post("/api/trigger_message")
    def api_trigger_message():
        data = request.get_json() or {}
        message = data.get("message")

        background_jobs.trigger_message(message)
        return jsonify({"status": "triggered"})

    @app.get("/settings")
    def get_settings():
        config = config_store.load()
        
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
            update_available=check_for_updates()
        )

    @app.get("/update")
    def get_update():
        current_branch = update_service.get_current_branch(timeout=5) or "unknown"
        configured_branch = config_store.get_str("git_branch", "main")
        return render_template(
            "update.html",
            display_name=_get_display_name(),
            update_check_interval=config_store.get_int("update_check_interval_seconds", 60),
            last_saved=_get_config_last_saved(),
            current_branch=current_branch,
            configured_branch=configured_branch,
            update_available=check_for_updates()
        )

    @app.get("/api-key")
    def get_api_key():
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
            api_key=config_store.get_str("api_key", ""),
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
        config_store.set_value("api_key", api_key)
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
            result = run_command(
                ["ssh-keygen", "-t", "ed25519", "-C", email, "-N", "", "-f", private_key],
                timeout_s=15,
                log_label="ssh_keygen",
            )
            
            if not result.ok:
                error_msg = result.stderr.strip() or result.stdout.strip() or result.error or "Unknown error"
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
            result = run_command(
                ["ssh-keygen", "-t", "ed25519", "-C", email, "-N", "", "-f", private_key],
                timeout_s=15,
                log_label="ssh_keygen_regen",
            )
            
            if not result.ok:
                error_msg = result.stderr.strip() or result.stdout.strip() or result.error or "Unknown error"
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
            result = run_command(
                ["sudo", "-u", "max", "git", "remote", "-v"],
                cwd=cwd,
                timeout_s=10,
                log_label="git_remote_list",
            )
            if result.ok and result.stdout:
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
            result = run_command(
                ["sudo", "-u", "max", "git", "remote", "set-url", "origin", ssh_url],
                cwd=cwd,
                timeout_s=10,
                log_label="git_remote_set",
            )
            if result.ok:
                return {"converted": True, "type": "ssh", "new_url": ssh_url}
            else:
                error_text = result.stderr.strip() or result.error or "Failed to update git remote"
                return {"converted": False, "type": "https", "error": error_text}
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
            result = run_command(
                ["sudo", "tailscale", "cert", "--cert-file", cert_file, "--key-file", key_file, hostname],
                timeout_s=60,
                log_label="tailscale_cert",
            )
            
            if not result.ok:
                error_msg = result.stderr.strip() or result.stdout.strip() or result.error or "Unknown error"
                return jsonify({"success": False, "error": error_msg}), 500
            
            # Verify files were created and change ownership to current user
            if os.path.exists(cert_file) and os.path.exists(key_file):
                # Change ownership of generated files to current user
                import pwd
                current_user = pwd.getpwuid(os.getuid()).pw_name
                run_command(
                    ["sudo", "chown", current_user, cert_file, key_file],
                    timeout_s=10,
                    log_label="tailscale_cert_chown",
                )
                return jsonify({
                    "success": True,
                    "cert_path": cert_file,
                    "key_path": key_file,
                    "message": "SSL certificates generated successfully. Restart the application to use HTTPS."
                })
            else:
                return jsonify({"success": False, "error": "Certificate generation succeeded but files not found"}), 500
                
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @app.get("/api/update/run")
    def api_update_run():
        def generate():
            _git_debug_log("api_update_run: Attempting to acquire git operation lock...")
            with background_jobs.git_operation(caller="api_update_run"):
                _git_debug_log("api_update_run: Lock acquired")
                try:
                    _git_debug_log("api_update_run: Starting 'git pull'")
                    process = update_service.popen_pull(
                        stdout=PIPE,
                        stderr=STDOUT,
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
                        _git_debug_log(f"api_update_run: git pull finished with exit_code={exit_code}")
                        _git_debug_log(f"api_update_run: git output: {combined_output[:500]}")
                        updates_found = has_updates(combined_output)
                        done_payload = {
                            "exit_code": exit_code,
                            "has_error": has_git_error(combined_output) or (exit_code != 0),
                            "has_updates": updates_found,
                        }
                        # If update succeeded with changes, get the latest commit message
                        if updates_found and not done_payload["has_error"]:
                            commit_message = update_service.get_latest_commit_message()
                            if commit_message:
                                done_payload["commit_message"] = commit_message
                        _git_debug_log(f"api_update_run: done_payload={done_payload}")
                        yield "event: done\n"
                        yield f"data: {json.dumps(done_payload)}\n\n"
                finally:
                    _git_debug_log("api_update_run: Releasing git operation lock")

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
        
        config_store.set_value("update_check_interval_seconds", interval)
        background_jobs.mark_settings_changed()
        return jsonify({"success": True, "interval": interval})

    @app.get("/api/check-for-updates")
    def api_check_for_updates():
        """
        Check if updates are available by running git fetch and comparing commits.
        Non-destructive - only checks, does not apply updates.
        """
        _git_debug_log("api_check_for_updates: Attempting to acquire git operation lock...")
        with background_jobs.git_operation(caller="api_check_for_updates"):
            _git_debug_log("api_check_for_updates: Lock acquired")
            try:
                try:
                    _git_debug_log("api_check_for_updates: Starting 'git fetch'")
                    fetch_result = update_service.fetch(timeout=30)
                    _git_debug_log(f"api_check_for_updates: git fetch completed with returncode={fetch_result.returncode}")
                    
                    if fetch_result.timed_out:
                        _git_debug_log("api_check_for_updates: git fetch timed out")
                        return jsonify({
                            "updates_available": False,
                            "error": "Git command timed out"
                        })
                    if not fetch_result.ok:
                        _git_debug_log(f"api_check_for_updates: git fetch failed: {fetch_result.stderr}")
                        return jsonify({
                            "updates_available": False,
                            "error": "Failed to fetch from remote"
                        })
                    
                    # Use configured branch for update check
                    config = config_store.load()
                    configured_branch = config.get("git_branch", "main")
                    local_head, remote_head = update_service.get_heads(timeout=10, branch=configured_branch)
                    if not local_head:
                        return jsonify({
                            "updates_available": False,
                            "error": "Failed to get local HEAD"
                        })
                    if not remote_head:
                        return jsonify({
                            "updates_available": False,
                            "error": "Could not determine remote branch"
                        })
                    
                    updates_available = local_head != remote_head
                    _git_debug_log(f"api_check_for_updates: local={local_head[:8]}, remote={remote_head[:8]}, updates_available={updates_available}")
                    
                    return jsonify({
                        "updates_available": updates_available,
                        "local_commit": local_head[:8],
                        "remote_commit": remote_head[:8]
                    })
                    
                except Exception as e:
                    _git_debug_log(f"api_check_for_updates: Exception: {e}")
                    return jsonify({
                        "updates_available": False,
                        "error": str(e)
                    })
            finally:
                _git_debug_log("api_check_for_updates: Releasing git operation lock")

    @app.get("/api/git-branches")
    def api_git_branches():
        """Get list of available remote git branches."""
        try:
            branches = update_service.get_remote_branches(timeout=10)
            return jsonify({"success": True, "branches": branches})
        except Exception as e:
            return jsonify({"success": False, "error": str(e), "branches": []}), 500

    @app.get("/api/current-branch")
    def api_current_branch():
        """Get the current local git branch."""
        try:
            branch = update_service.get_current_branch(timeout=5)
            if branch:
                return jsonify({"success": True, "branch": branch})
            else:
                return jsonify({"success": False, "error": "Could not determine current branch", "branch": None})
        except Exception as e:
            return jsonify({"success": False, "error": str(e), "branch": None}), 500

    @app.post("/api/switch-branch")
    def api_switch_branch():
        """Switch to a different git branch."""
        data = request.get_json() or {}
        branch = data.get("branch", "").strip()
        
        if not branch:
            return jsonify({"success": False, "error": "Branch name is required"}), 400
        
        # Validate branch name (basic sanitization)
        import re
        if not re.match(r'^[\w./-]+$', branch):
            return jsonify({"success": False, "error": "Invalid branch name"}), 400
        
        _git_debug_log(f"api_switch_branch: Attempting to switch to branch '{branch}'")
        
        with background_jobs.git_operation(caller="api_switch_branch"):
            _git_debug_log("api_switch_branch: Lock acquired")
            try:
                result = update_service.switch_branch(branch, timeout=60)
                
                if result["success"]:
                    # Save the branch to config
                    config_store.set_value("git_branch", branch)
                    _git_debug_log(f"api_switch_branch: Successfully switched to branch '{branch}'")
                    return jsonify({
                        "success": True,
                        "branch": branch,
                        "message": result.get("message", f"Switched to branch '{branch}'")
                    })
                else:
                    _git_debug_log(f"api_switch_branch: Failed to switch branch: {result.get('error')}")
                    return jsonify({
                        "success": False,
                        "error": result.get("error", "Unknown error switching branch")
                    }), 500
            except Exception as e:
                _git_debug_log(f"api_switch_branch: Exception: {e}")
                return jsonify({"success": False, "error": str(e)}), 500
            finally:
                _git_debug_log("api_switch_branch: Releasing git operation lock")

    @app.post("/api/restart")
    def api_restart():
        # Alias for /api/reboot - kept for backward compatibility but redirects to reboot logic
        def _do_reboot():
            try:
                time.sleep(0.25)
                system_service.reboot()
            except Exception:
                raise

        threading.Thread(target=_do_reboot, daemon=True).start()
        return jsonify({"status": "rebooting"})

    @app.get("/system-management")
    def get_system_management():
        config = config_store.load()
        return render_template("system_management.html", config=config, display_name=_get_display_name())

    @app.post("/api/reboot")
    def api_reboot():
        # Execute reboot command matching main_display.py implementation
        def _do_reboot():
            try:
                time.sleep(0.25)
                system_service.reboot()
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
                system_service.shutdown()
            except Exception:
                raise

        threading.Thread(target=_do_shutdown, daemon=True).start()
        return jsonify({"status": "shutting down"})

    @app.get("/api/reboot-config")
    def api_get_reboot_config():
        return jsonify({
            "reboot_enabled": config_store.get_bool("reboot_enabled", False),
            "reboot_time": config_store.get_str("reboot_time", "12:00 AM")
        })

    @app.get("/api/reboot-warning")
    def api_reboot_warning():
        return jsonify(_get_reboot_warning_status())

    @app.post("/api/reboot-config")
    def api_post_reboot_config():
        data = request.get_json()
        updates = {}
        
        # Update reboot_enabled
        if "reboot_enabled" in data:
            updates["reboot_enabled"] = bool(data["reboot_enabled"])
        
        # Update reboot_time from three components
        if "reboot_hour" in data and "reboot_minute" in data and "reboot_ampm" in data:
            hour = data["reboot_hour"]
            minute = data["reboot_minute"]
            ampm = data["reboot_ampm"]
            time_str = f"{hour}:{minute} {ampm}"
            updates["reboot_time"] = time_str

        if updates:
            config_store.set_values(updates)
        
        return jsonify({"status": "saved"})

    @app.post("/settings")
    def post_settings():
        form = request.form

        def as_bool(name):
            return form.get(name) in ("true", "True", "1", "on", "yes")

        updates = {}
        # Update simple flags
        updates["show_countdown"] = as_bool("show_countdown")
        updates["show_clock"] = as_bool("show_clock")
        updates["filter_by_direction"] = as_bool("filter_by_direction")
        updates["filter_by_destination_direction"] = as_bool("filter_by_destination_direction")
        updates["reboot_enabled"] = as_bool("reboot_enabled")
        updates["screen_sleep_enabled"] = as_bool("screen_sleep_enabled")

        # Update numeric values
        minutes = form.get("screen_sleep_minutes")
        try:
            minutes_val = int(minutes) if minutes is not None else None
        except ValueError:
            minutes_val = None
        if minutes_val is not None:
            updates["screen_sleep_minutes"] = minutes_val

        # Update refresh rate
        refresh_rate = form.get("refresh_rate_seconds")
        try:
            refresh_rate_val = int(refresh_rate) if refresh_rate is not None else None
        except ValueError:
            refresh_rate_val = None
        if refresh_rate_val is not None:
            updates["refresh_rate_seconds"] = refresh_rate_val

        # Update API timeout
        api_timeout = form.get("api_timeout_seconds")
        try:
            api_timeout_val = int(api_timeout) if api_timeout is not None else None
        except ValueError:
            api_timeout_val = None
        if api_timeout_val is not None:
            updates["api_timeout_seconds"] = api_timeout_val

        # Update selections
        selected_line = form.get("selected_line")
        if selected_line is not None:
            updates["selected_line"] = selected_line

        selected_station = form.get("selected_station")
        if selected_station is not None:
            updates["selected_station"] = selected_station

        selected_destination = form.get("selected_destination")
        if selected_destination is not None:
            updates["selected_destination"] = selected_destination

        # Update title text
        title_text = form.get("title_text")
        if title_text is not None:
            updates["title_text"] = title_text

        # Handle timezone setting (system-only, not saved to config)
        timezone = form.get("timezone")
        if timezone:
            # Apply timezone system-wide via timedatectl
            try:
                result = run_command(
                    ["sudo", "timedatectl", "set-timezone", timezone],
                    timeout_s=10,
                    log_label="timezone_set",
                )
                # Refresh Python's timezone cache after setting system timezone
                if result.ok:
                    time.tzset()
            except Exception:
                pass

        # Reboot time from three components
        reboot_hour = form.get("reboot_hour")
        reboot_minute = form.get("reboot_minute")
        reboot_ampm = form.get("reboot_ampm")
        if reboot_hour and reboot_minute and reboot_ampm:
            time_str = f"{reboot_hour}:{reboot_minute} {reboot_ampm}"
            updates["reboot_time"] = time_str

        if updates:
            config_store.set_values(updates)

        # Trigger settings changed flag for main display to refresh
        background_jobs.mark_settings_changed()

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

    def _get_installed_fonts():
        """Get list of installed fonts with their file paths using fc-list.
        
        Returns:
            list of dict: Each dict has 'name' (font family) and 'file' (path to font file)
        """
        try:
            # Get font family names and their file paths
            result = run_command(
                ["fc-list", "--format=%{family}|%{file}\n"],
                timeout_s=10,
                log_label="font_list",
            )
            if result.ok:
                # Parse font names and paths, deduplicate by family name
                fonts = {}
                for line in result.stdout.strip().splitlines():
                    if "|" not in line:
                        continue
                    family_part, file_path = line.split("|", 1)
                    file_path = file_path.strip()
                    
                    # fc-list can return comma-separated family names, use first one
                    for font_name in family_part.split(","):
                        font_name = font_name.strip()
                        if font_name and font_name not in fonts:
                            # Only include common font formats
                            if file_path.lower().endswith(('.ttf', '.otf', '.woff', '.woff2')):
                                fonts[font_name] = file_path
                                break
                
                # Sort by font name and return as list of dicts
                return [{"name": name, "file": path} for name, path in sorted(fonts.items(), key=lambda x: x[0].lower())]
        except Exception:
            pass
        # Fallback fonts if fc-list fails (e.g., on Windows)
        return [{"name": f, "file": ""} for f in ["Quicksand", "Arial", "Helvetica", "Sans-Serif", "Serif", "Monospace"]]

    def _get_font_path(font_name):
        """Get the file path for a specific font by name."""
        try:
            result = run_command(
                ["fc-list", f":family={font_name}", "--format=%{file}\n"],
                timeout_s=5,
                log_label="font_path_lookup",
            )
            if result.ok:
                for line in result.stdout.strip().splitlines():
                    path = line.strip()
                    if path and os.path.exists(path):
                        return path
        except Exception:
            pass
        return None

    @app.get("/api/font-file/<path:font_name>")
    def api_font_file(font_name):
        """Serve a font file by font family name."""
        from flask import send_file
        import urllib.parse
        
        # URL decode the font name
        font_name = urllib.parse.unquote(font_name)
        
        font_path = _get_font_path(font_name)
        if font_path and os.path.exists(font_path):
            # Determine mime type based on extension
            ext = os.path.splitext(font_path)[1].lower()
            mime_types = {
                '.ttf': 'font/ttf',
                '.otf': 'font/otf',
                '.woff': 'font/woff',
                '.woff2': 'font/woff2',
            }
            mime_type = mime_types.get(ext, 'application/octet-stream')
            return send_file(font_path, mimetype=mime_type)
        
        return jsonify({"error": "Font not found"}), 404

    @app.get("/change-font")
    def get_change_font():
        current_font = config_store.get_str("font_family", "Quicksand")
        default_font = config_store.default_config.get("font_family", "Quicksand")
        installed_fonts = _get_installed_fonts()
        return render_template(
            "change_font.html",
            fonts=installed_fonts,
            current_font=current_font,
            default_font=default_font,
            display_name=_get_display_name()
        )

    @app.post("/api/font")
    def api_set_font():
        """Set the application font."""
        data = request.get_json() or {}
        font_family = data.get("font_family", "").strip()
        
        if not font_family:
            return jsonify({"success": False, "error": "Font family is required"}), 400
        
        config_store.set_value("font_family", font_family)
        
        # Trigger settings changed flag for main display
        background_jobs.mark_settings_changed()
        
        return jsonify({"success": True, "font_family": font_family})

    @app.post("/api/font/revert")
    def api_revert_font():
        """Revert font to default."""
        default_font = config_store.default_config.get("font_family", "Quicksand")
        config_store.set_value("font_family", default_font)
        
        # Trigger settings changed flag for main display
        background_jobs.mark_settings_changed()
        
        return jsonify({"success": True, "font_family": default_font})

    def _get_user_fonts_dir():
        """Get the user-local fonts directory path."""
        return os.path.expanduser("~/.local/share/fonts")

    def _install_font(file_storage):
        """
        Install an uploaded font file to the user-local fonts directory.
        
        Args:
            file_storage: werkzeug FileStorage object from file upload
            
        Returns:
            dict: {"success": True, "font_name": "...", "message": "..."} or 
                  {"success": False, "error": "..."}
        """
        from werkzeug.utils import secure_filename
        
        # Validate file exists
        if not file_storage or not file_storage.filename:
            return {"success": False, "error": "No file provided"}
        
        # Get and validate filename
        original_filename = file_storage.filename
        ext = os.path.splitext(original_filename)[1].lower()
        
        if ext not in ('.ttf', '.otf'):
            return {"success": False, "error": "Only .ttf and .otf files are supported"}
        
        # Read file content for validation
        file_content = file_storage.read()
        file_storage.seek(0)  # Reset for later saving
        
        # Check file size (max 10MB)
        if len(file_content) > 10 * 1024 * 1024:
            return {"success": False, "error": "File too large (max 10MB)"}
        
        # Validate file magic bytes
        # TTF: starts with \x00\x01\x00\x00 or 'true' or 'typ1'
        # OTF: starts with 'OTTO'
        valid_magic = False
        if len(file_content) >= 4:
            magic = file_content[:4]
            if magic == b'\x00\x01\x00\x00':  # TTF
                valid_magic = True
            elif magic == b'OTTO':  # OTF
                valid_magic = True
            elif magic == b'true':  # TTF variant
                valid_magic = True
            elif magic == b'typ1':  # TTF variant
                valid_magic = True
        
        if not valid_magic:
            return {"success": False, "error": "Invalid font file format"}
        
        # Secure the filename
        safe_filename = secure_filename(original_filename)
        if not safe_filename:
            safe_filename = f"uploaded_font{ext}"
        
        # Ensure fonts directory exists
        fonts_dir = _get_user_fonts_dir()
        try:
            os.makedirs(fonts_dir, exist_ok=True)
        except Exception as e:
            return {"success": False, "error": f"Failed to create fonts directory: {str(e)}"}
        
        # Save the file
        font_path = os.path.join(fonts_dir, safe_filename)
        try:
            file_storage.save(font_path)
        except Exception as e:
            return {"success": False, "error": f"Failed to save font file: {str(e)}"}
        
        # Refresh font cache
        try:
            run_command(
                ["fc-cache", "-f"],
                timeout_s=30,
                log_label="font_cache_refresh",
            )
        except Exception:
            # Font is installed but cache refresh failed - not critical
            pass
        
        # Get font family name using fc-query
        font_name = None
        try:
            result = run_command(
                ["fc-query", "--format=%{family}", font_path],
                timeout_s=10,
                log_label="font_query",
            )
            if result.ok and result.stdout.strip():
                # fc-query may return comma-separated names, take first
                font_name = result.stdout.strip().split(",")[0].strip()
        except Exception:
            pass
        
        if not font_name:
            # Fallback: use filename without extension
            font_name = os.path.splitext(safe_filename)[0]
        
        return {
            "success": True,
            "font_name": font_name,
            "filename": safe_filename,
            "message": f"Font '{font_name}' installed successfully"
        }

    @app.post("/api/font/upload")
    def api_upload_font():
        """Upload and install a new font file."""
        if 'font_file' not in request.files:
            return jsonify({"success": False, "error": "No font file provided"}), 400
        
        font_file = request.files['font_file']
        result = _install_font(font_file)
        
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400

    @app.post("/api/restart-app")
    def api_restart_app():
        """Restart the main display application."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            main_display_script = os.path.join(script_dir, "main_display.py")
            
            # Launch new instance of main_display.py
            start_process(
                ["python3", main_display_script, "--fullscreen"],
                cwd=script_dir,
                start_new_session=True,
                log_label="restart_app",
                timeout_s=None,
            )
            
            # Schedule the current process to exit after response is sent
            def exit_app():
                time.sleep(0.5)
                os._exit(0)
            
            exit_thread = threading.Thread(target=exit_app, daemon=True)
            exit_thread.start()
            
            return jsonify({"success": True, "message": "Restarting application..."})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

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
