import json
import os

# Use absolute path based on repository root
CONFIG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.json"))

DEFAULT_CONFIG = {
    "api_key": "",
    "show_clock": True,
    "reboot_enabled": False,
    "reboot_time": "12:00 AM",
    "screen_sleep_enabled": False,
    "screen_sleep_minutes": 5,
    "refresh_rate_seconds": 30,
    "title_text": "Nicole's Train Tracker!",
    "update_check_interval_seconds": 60,
    "font_family": "Quicksand",
}


def load_config():
    """Load configuration from JSON file."""
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        return {**DEFAULT_CONFIG, **config}
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(key, value):
    """Update a specific config value and save to file."""
    config = load_config()
    config[key] = value

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


class ConfigStore:
    """Provides load/save access to config data."""

    def load(self):
        return load_config()

    def save(self, key, value):
        save_config(key, value)

    @property
    def path(self):
        return CONFIG_FILE

    @property
    def default_config(self):
        return DEFAULT_CONFIG
