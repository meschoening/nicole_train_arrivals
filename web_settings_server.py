import threading
from flask import Flask, request, jsonify, render_template, redirect, url_for, Response
import config_handler
import os
from datetime import datetime
import subprocess
import sys
import time
import json


_data_lock = threading.Lock()


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


def start_web_settings_server(data_handler, host="0.0.0.0", port=80):
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

    @app.get("/settings")
    def get_settings():
        config = config_handler.load_config()
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
            last_saved=_get_config_last_saved(),
        )

    @app.get("/")
    def index():
        return render_template("index.html", device_ip=_get_device_ip())

    @app.get("/update")
    def get_update():
        # Simple page render; live behavior wired via JS
        return render_template("update.html")

    @app.get("/api-key")
    def get_api_key():
        config = config_handler.load_config()
        return render_template("api_key.html", api_key=config.get("api_key", ""), last_saved=_get_config_last_saved())

    @app.post("/api-key")
    def post_api_key():
        api_key = request.form.get("api_key", "")
        config_handler.save_config("api_key", api_key)
        return redirect(url_for("index"))

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
                done_payload = {
                    "exit_code": exit_code,
                    "has_error": _has_git_error(combined_output) or (exit_code != 0),
                    "has_updates": _has_updates(combined_output),
                }
                yield "event: done\n"
                yield f"data: {json.dumps(done_payload)}\n\n"

        headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # for some proxies
        }
        return Response(generate(), mimetype="text/event-stream", headers=headers)

    @app.post("/api/restart")
    def api_restart():
        # Restart the entire application shortly after returning a response
        def _do_restart():
            try:
                time.sleep(0.25)
                script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'main_display.py'))
                os.execv(sys.executable, [sys.executable, script_path])
            except Exception:
                # If exec fails, process will continue running; no silent pass
                raise

        threading.Thread(target=_do_restart, daemon=True).start()
        return jsonify({"status": "restarting"})

    @app.get("/system-management")
    def get_system_management():
        config = config_handler.load_config()
        return render_template("system_management.html", config=config)

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

        # Reboot time from three components
        reboot_hour = form.get("reboot_hour")
        reboot_minute = form.get("reboot_minute")
        reboot_ampm = form.get("reboot_ampm")
        if reboot_hour and reboot_minute and reboot_ampm:
            time_str = f"{reboot_hour}:{reboot_minute} {reboot_ampm}"
            config_handler.save_config("reboot_time", time_str)

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
        app.run(host=host, port=port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


