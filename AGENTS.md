# Repository Guidelines

## Project Structure & Module Organization
- Root Python modules: `main_display.py` (PyQt5 UI + app startup), `web_settings_server.py` (Flask settings server), `MetroAPI.py` (WMATA API), `data_handler.py` (caching), `services/config_store.py` and `services/message_store.py` (local JSON settings), `wifi_setup.py` and `wifi_portal_server.py` (provisioning flow).
- Web UI templates live in `templates/` and are Jinja-rendered HTML pages.
- Static assets (fonts) live in `assets/`.
- Deployment and system notes live in `docs/` (see `docs/README.md`, `docs/PORT80_SETUP.md`, `docs/SUDO_COMMANDS.txt`).

## Build, Test, and Development Commands
- Run the main display: `python3 main_display.py` (add `--fullscreen` for kiosk mode). This also starts the embedded settings web server.
- Run WiFi setup UI: `python3 wifi_setup.py --fullscreen` (useful when no WiFi is configured).
- Run only the WiFi portal server (for debugging): `python3 wifi_portal_server.py`.
- There is no build step; dependencies are system packages (PyQt5, Flask, requests, pandas). See `docs/redeployment_steps.txt` for provisioning commands.

## Coding Style & Naming Conventions
- Python uses 4-space indentation, `snake_case` for functions/vars, `CamelCase` for classes, and `UPPER_SNAKE_CASE` constants (see `services/config_store.py`).
- Keep UI styling in Qt stylesheets for the desktop app and in the HTML templates for web UI.
- Prefer module-level helper functions for cross-cutting concerns rather than duplicating subprocess logic.
- Avoid leading underscores in helper method names; use public-style helpers for UI builders.

## Testing Guidelines
- No automated tests are currently present. If adding tests, place them in a `tests/` directory and use `pytest` naming (`test_*.py`).
- Manual test checklist should include: startup with/without WiFi, web settings updates, API key entry, and update/reboot flows.

## Commit & Pull Request Guidelines
- Recent history uses short, sentence-case messages without prefixes (e.g., “Update README”, “Clean for delivery”). Follow that style and keep messages concise.
- PRs should include a short summary and screenshots for UI changes (Qt or web); omit testing sections unless explicitly requested. Link related issues if applicable.
- When addressing any item from `CODE_REVIEW.md`, update that section to yellow and replace its recommendation with an update note, matching the existing format.

## Security & Configuration Tips
- Local settings are stored in `config.json` and `messages.json`; do not commit secrets or API keys.
- WiFi provisioning and system actions rely on passwordless sudo for specific commands; see `docs/SUDO_COMMANDS.txt`.
- Binding the web server to port 80 requires capability setup; see `docs/PORT80_SETUP.md`.
