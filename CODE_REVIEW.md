# Code Review

## Scope
Reviewed the Python application (PyQt5 main display, Flask settings server, WiFi portal), supporting handlers, and HTML templates.
<span style="color: yellow;">Yellow text indicates issue has been addressed but not tested,</span> <span style="color: green;">green text indicates change has been tested and validated as stable.</span>

## Findings

### [High] Scheduled reboot crashes due to `datetime.timedelta`
- **Description:** `check_reboot_schedule` calls `datetime.timedelta(...)` even though `datetime` is the class imported from `datetime` and does not expose `timedelta` (`main_display.py:2359`).
- **Why it matters:** When auto-reboot is enabled, this raises `AttributeError`, breaking the reboot scheduler and potentially spamming the UI/logs or halting the timer loop.
- **Recommendation:** Replace with the imported `timedelta` (`warning_datetime - timedelta(seconds=60)`), and add a small test or manual verification for the scheduled reboot path.

### [High] Admin web endpoints are unauthenticated
- **Description:** The web server exposes sensitive actions (update, reboot, shutdown, SSH key generation, SSL cert generation, timezone changes) without authentication or CSRF protection (`web_settings_server.py:525`, `web_settings_server.py:704`, `web_settings_server.py:797`, `web_settings_server.py:982`, `web_settings_server.py:1001`, `web_settings_server.py:1014`).
- **Why it matters:** Anyone on the network (including in AP/captive mode) can trigger system updates, reboots, or key generation. This is a high-impact security exposure.
- **Recommendation:** Add an auth layer (shared secret/token, HTTP basic auth, or Tailscale-only access), CSRF protection for POSTs, and consider binding the server to localhost by default with explicit opt-in for remote access.

### [High] Jinja loop for `@font-face` is malformed
- **Description:** The `change_font` template includes a broken Jinja loop (`templates/change_font.html:9-22`). The `{% for %}` and `{% endfor %}` tags are separated and will render as literal text; `{{ font.name }}` becomes undefined.
- **Why it matters:** The dynamic `@font-face` declarations do not render, so font previews and loading are unreliable or broken.
- **Recommendation:** Fix the template tags to proper Jinja syntax:
  ```jinja
  {% for font in fonts %}
  @font-face {
    font-family: '{{ font.name }}';
    src: url('/api/font-file/{{ font.name | urlencode }}') format('truetype');
    font-display: swap;
  }
  {% endfor %}
  ```

### [Medium] Captive portal server never stops
- **Description:** `start_portal_server` spins up a Flask server thread; `stop_portal_server` only flips a flag and does not actually stop the server (`wifi_setup.py:884-899`).
- **Why it matters:** After “Close Setup Network,” the portal continues listening on port 80. Re-entering broadcast mode will likely fail to bind the port, and the portal may remain accessible on the LAN.
- **Recommendation:** Use a stoppable server (`werkzeug.serving.make_server`) or a dedicated process you can terminate. Also guard against multiple starts by checking `portal_server_running` before spawning a new thread.

### [Medium] SSID rendering allows JS injection in captive portal
- **Description:** The WiFi portal builds inline `onclick` handlers with SSIDs embedded in JS strings (`templates/wifi_setup.html:279-299`). `escapeHtml` is HTML-safe but not JS-string-safe; HTML entities are decoded before the JS executes.
- **Why it matters:** A malicious SSID containing quotes can break out of the string and inject script into the captive portal UI (XSS).
- **Recommendation:** Avoid inline JS. Build DOM nodes and attach listeners with `addEventListener`, storing SSIDs in `data-*` attributes or closures; use `textContent` for display.

### <span style="color: yellow;">[Medium] Config/message writes are non-atomic and not synchronized</span>
- <span style="color: yellow;">**Description:** `ConfigStore.set_values` and `save_messages` performed read-modify-write without file locks or atomic writes (`services/config_store.py`, `services/message_store.py`).</span>
- <span style="color: yellow;">**Why it matters:** The UI and web server can write concurrently, leading to lost updates or a partially written JSON file.</span>
- <span style="color: yellow;">**Update:** Config and message writes now take an exclusive lock and write atomically (temp file + `os.replace`) via `services/file_store.py`.</span>

### [Medium] Network calls have no timeout and run on the UI thread
- **Description:** Metro API requests omit timeouts (`MetroAPI.py:38`, `MetroAPI.py:66`, `MetroAPI.py:91`), and the UI refresh path calls them directly on the Qt thread (`main_display.py:1544-1568`).
- **Why it matters:** A stalled network call can freeze the UI, blocking input and timers.
- **Recommendation:** Add conservative timeouts (e.g., 3–5 seconds) and move API fetches to a worker thread (Qt `QRunnable`/`QThreadPool`) or async worker that updates the UI on completion.

### <span style="color: green;">[Low] Update check interval changes do not propagate to running app</span>
- <span style="color: green;">**Description:** The update check timer interval is read once on startup and never updated when `update_check_interval_seconds` changes (`main_display.py:700-704` vs. `main_display.py:1654-1718`).
- <span style="color: green;">**Why it matters:** The web UI indicates the interval was saved, but the running display ignores it until restart.</span>
- <span style="color: green;">**Update:** Config change notifications now refresh the update check timer interval at runtime.</span>

### [Low] Hard-coded username in git operations
- **Description:** Git operations are run as the fixed user `max` (`web_settings_server.py:634`, `web_settings_server.py:679`, `web_settings_server.py:811`).
- **Why it matters:** This breaks portability and will fail on systems without that user or where file ownership differs.
- **Recommendation:** Use the current user (from `os.getuid()`/`pwd.getpwuid`) or make the git user configurable in the config file.

## Testing Gaps
- No automated tests for config/message migrations, scheduled reboot logic, or update flows. A small test suite with mocked subprocesses and API responses would catch regressions in these critical paths.
- No coverage for web endpoints (update/run, reboot/shutdown, font upload). Basic integration tests using Flask’s test client would help validate request/response handling and error paths.

## Architecture and General Coding Practices
- <span style="color: green;">**Architecture:** The application’s responsibilities are tightly coupled, especially in `main_display.py` (UI, networking, system control, git updates, and server lifecycle in one module). This makes it harder to reason about side effects and increases the risk that UI changes break system-management behavior.
  - **Update:** Split UI, system actions, update flow, and API access into focused modules and injected them into `MainWindow`; verified the display and settings server behaviors remain stable.</span>
- <span style="color: green;">**Concurrency model:** Background work is split across QTimers, QProcess, and threads, with some shared flags in `web_settings_server.py`. Coordination is mostly ad hoc (e.g., shared “git in progress” flags).
  - **Update:** Centralized shared state in `services/background_jobs.py` with a single interface for background jobs; Qt signals/slots now handle cross-thread updates to avoid subtle races.</span>
- <span style="color: green;">**I/O boundaries:** Direct `os.system` and `subprocess` calls are scattered across UI and server code, and error handling is inconsistent (sometimes logged, sometimes suppressed).
  - **Update:** Added `services/system_actions.py` and routed system commands through `run_command`/`start_process` with consistent logging, explicit timeouts, and structured error reporting across UI, server, and WiFi provisioning code.</span>
- <span style="color: green;">**Configuration flow:** Config reads/writes are duplicated in several paths (UI refresh, web settings, startup). This increases the chance of inconsistent behavior when new settings are added.
  - **Update:** Centralized config access with typed getters/setters, validation, and change notifications to keep timers/UI in sync (not yet validated).</span>
- <span style="color: green;">**Code hygiene:** Some functions are very long and mix responsibilities (e.g., UI construction + business logic in the same method).
  - **Update:** Extracted UI builder helpers and shortened long methods in key screens; manual smoke checks show no regressions.</span>

## Acceptable As-Is
- Message migration logic in `message_handler.load_messages` is clear and backward-compatible.
- The use of `QProcess` for git pull/fetch keeps the UI responsive under normal conditions.
- Data caching in `DataHandler` is straightforward and appropriate for reducing API calls.

## Priority Summary
1. Fix scheduled reboot crash (`main_display.py:2359`).
2. Add authentication/CSRF protection to the web control plane (`web_settings_server.py`).
3. Repair the `change_font` template loop so fonts load correctly (`templates/change_font.html:9-22`).
4. Make the captive portal server stoppable and prevent multiple bind attempts (`wifi_setup.py:884-899`).
5. Remove JS injection risk in SSID rendering (`templates/wifi_setup.html:279-299`).
6. Add atomic writes/locking for config and messages (`config_handler.py`, `message_handler.py`).
7. Add timeouts + background fetching for Metro API requests (`MetroAPI.py`, `main_display.py`).
8. Apply update check interval changes at runtime (`main_display.py`).
9. Remove the hard-coded git username (`web_settings_server.py`).
