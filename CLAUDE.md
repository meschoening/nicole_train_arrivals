# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nicole's Train Tracker is a PyQt5 kiosk application displaying WMATA (Washington Metro) train arrival predictions. Designed for embedded systems (Raspberry Pi with DietPi) with touchscreen displays.

## Commands

```bash
# Run main display (also starts embedded Flask settings server)
python3 main_display.py
python3 main_display.py --fullscreen  # Kiosk mode

# WiFi setup UI (when no WiFi configured)
python3 wifi_setup.py --fullscreen

# WiFi portal server standalone
python3 wifi_portal_server.py
```

No build step. Dependencies are system packages (PyQt5, Flask, requests, pandas).

**Verify Python files import correctly:**
```bash
python3 -c "import main_display"
python3 -c "import web_settings_server"
python3 -c "import wifi_setup"
```

## Architecture

**Entry Points:**
- `main_display.py` - PyQt5 desktop UI + app startup logic + embedded settings server
- `web_settings_server.py` - Flask web server for remote configuration (runs in thread from main_display)
- `wifi_setup.py` / `wifi_portal_server.py` - WiFi provisioning flow

**Core Services (`services/`):**
- `config_store.py` - JSON config with validation, pub/sub pattern for change notifications
- `message_store.py` - Message scheduling system
- `user_store.py` - User auth with PBKDF2-SHA256 hashing
- `system_service.py` - System ops (WiFi, display, reboot via subprocess)
- `update_service.py` - Git-based auto-update system
- `background_jobs.py` - Cross-thread signal coordination (PyQt5 signals)

**Data Layer:**
- `MetroAPI.py` - WMATA API client wrapper
- `data_handler.py` - API response caching

**UI Components (`views/`):**
- `popouts.py` - Modal UI elements
- `filters.py` - Event filters
- `overlays.py` - Display overlays

**Web UI:**
- `templates/` - Jinja2 HTML templates for Flask settings server

## Key Patterns

**Threading:** `PredictionsFetchWorker` (QRunnable) for non-blocking API calls; `BackgroundJobCoordinator` for inter-thread signals; web server runs in separate thread from PyQt5 main loop.

**Config Validation:** `ConfigField` dataclass with type coercion, regex validators, min/max bounds. All config changes go through `ConfigStore.set()` which validates and notifies subscribers.

**System Commands:** Passwordless sudo for specific commands (see `docs/SUDO_COMMANDS.txt`). Use `system_actions.py` subprocess wrapper with timeout/logging.

**File Operations:** `file_store.py` provides atomic JSON writes with fcntl-based locking for concurrent access.

## Code Style

- 4-space indentation, `snake_case` functions/vars, `CamelCase` classes, `UPPER_SNAKE_CASE` constants
- Qt stylesheets for desktop UI styling; Jinja templates for web UI
- Prefer module-level helper functions over duplicating subprocess logic
- Avoid leading underscores in helper method names

## Commits

Short, sentence-case messages without prefixes (e.g., "Update README", "Clean for delivery"). Keep messages concise. If addressing items from `CODE_REVIEW.md`, update that section to yellow status with an update note.

## Configuration Files

- `config.json` - Runtime settings (git-ignored, contains API key)
- `messages.json` - Message scheduling config
- `users.json` - User accounts (git-ignored)
