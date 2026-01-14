import json
import os
import re
from dataclasses import dataclass

from services.file_store import atomic_write_json, file_lock

# Use absolute path based on repository root
CONFIG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.json"))


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValueError("Invalid boolean string")
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError("Invalid boolean value")


def _coerce_int(value):
    if isinstance(value, bool):
        return int(value)
    return int(value)


def _coerce_str(value):
    if value is None:
        return ""
    return str(value)


def _coerce_optional_str(value):
    if value is None:
        return None
    return str(value)


def _clamp(min_value, max_value):
    def _inner(value):
        return max(min_value, min(max_value, value))
    return _inner


def _matches_reboot_time(value):
    if not isinstance(value, str):
        return False
    return re.match(r"^\d{1,2}:\d{2} (AM|PM)$", value) is not None


def _matches_branch(value):
    if not isinstance(value, str):
        return False
    return re.match(r"^[\w./-]+$", value) is not None


@dataclass(frozen=True)
class ConfigField:
    default: object
    caster: object
    validator: object = lambda value: True
    normalizer: object = None

    def coerce_for_load(self, value):
        try:
            candidate = self.caster(value)
        except (TypeError, ValueError):
            return self.default
        if self.normalizer is not None:
            candidate = self.normalizer(candidate)
        if not self.validator(candidate):
            return self.default
        return candidate

    def coerce_for_update(self, value):
        try:
            candidate = self.caster(value)
        except (TypeError, ValueError):
            return None, False
        if self.normalizer is not None:
            candidate = self.normalizer(candidate)
        if not self.validator(candidate):
            return None, False
        return candidate, True


CONFIG_SCHEMA = {
    "api_key": ConfigField("", _coerce_str),
    "show_clock": ConfigField(True, _coerce_bool),
    "reboot_enabled": ConfigField(False, _coerce_bool),
    "reboot_time": ConfigField("12:00 AM", _coerce_str, validator=_matches_reboot_time),
    "screen_sleep_enabled": ConfigField(False, _coerce_bool),
    "screen_sleep_minutes": ConfigField(
        5,
        _coerce_int,
        validator=lambda value: 1 <= value <= 30,
        normalizer=_clamp(1, 30),
    ),
    "refresh_rate_seconds": ConfigField(
        30,
        _coerce_int,
        validator=lambda value: 5 <= value <= 120,
        normalizer=_clamp(5, 120),
    ),
    "api_timeout_seconds": ConfigField(
        5,
        _coerce_int,
        validator=lambda value: 1 <= value <= 15,
        normalizer=_clamp(1, 15),
    ),
    "title_text": ConfigField("Nicole's Train Tracker!", _coerce_str),
    "update_check_interval_seconds": ConfigField(
        60,
        _coerce_int,
        validator=lambda value: 5 <= value <= 3600,
        normalizer=_clamp(5, 3600),
    ),
    "update_requires_reboot": ConfigField(False, _coerce_bool),
    "update_console_output": ConfigField("", _coerce_str),
    "update_commit_message": ConfigField("", _coerce_str),
    "update_boot_id": ConfigField("", _coerce_str),
    "font_family": ConfigField("Quicksand", _coerce_str),
    "git_branch": ConfigField("main", _coerce_str, validator=_matches_branch),
    "selected_line": ConfigField(None, _coerce_optional_str, validator=lambda value: value is None or isinstance(value, str)),
    "selected_station": ConfigField(None, _coerce_optional_str, validator=lambda value: value is None or isinstance(value, str)),
    "selected_destination": ConfigField(None, _coerce_optional_str, validator=lambda value: value is None or isinstance(value, str)),
    "show_countdown": ConfigField(True, _coerce_bool),
    "filter_by_direction": ConfigField(False, _coerce_bool),
    "filter_by_destination_direction": ConfigField(False, _coerce_bool),
    "web_session_secret": ConfigField("", _coerce_str),
    "initial_admin_username": ConfigField("", _coerce_str),
    "initial_admin_password": ConfigField("", _coerce_str),
}

DEFAULT_CONFIG = {key: field.default for key, field in CONFIG_SCHEMA.items()}


def _read_config_raw():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _normalize_config(raw_config):
    normalized = {}
    for key, field in CONFIG_SCHEMA.items():
        normalized[key] = field.coerce_for_load(raw_config.get(key, field.default))
    for key, value in raw_config.items():
        if key not in CONFIG_SCHEMA:
            normalized[key] = value
    return normalized


def load_config():
    """Load configuration from JSON file."""
    return _normalize_config(_read_config_raw())


def save_config(key, value):
    """Update a specific config value and save to file."""
    store = ConfigStore()
    store.set_value(key, value)


class ConfigStore:
    """Central access to config with validation and change notifications."""

    def __init__(self):
        self._listeners = []
        self._last_notified_config = load_config()

    def load(self):
        return load_config()

    def get_value(self, key, default=None):
        config = self.load()
        if key in config:
            return config[key]
        return default

    def get_bool(self, key, default=None):
        value = self.get_value(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default if default is not None else False
        try:
            return _coerce_bool(value)
        except (TypeError, ValueError):
            return default if default is not None else False

    def get_int(self, key, default=None):
        value = self.get_value(key, default)
        if value is None:
            return default
        try:
            return _coerce_int(value)
        except (TypeError, ValueError):
            return default

    def get_str(self, key, default=None):
        value = self.get_value(key, default)
        if value is None:
            return default
        return str(value)

    def set_value(self, key, value):
        updated_config, _ = self.set_values({key: value})
        return updated_config.get(key)

    def set_values(self, updates):
        lock_path = f"{CONFIG_FILE}.lock"
        with file_lock(lock_path):
            raw_config = _read_config_raw()
            updated_config = dict(raw_config)
            changed_keys = set()

            for key, value in updates.items():
                field = CONFIG_SCHEMA.get(key)
                if field is None:
                    continue
                current = updated_config.get(key, field.default)
                candidate, valid = field.coerce_for_update(value)
                if not valid:
                    continue
                if candidate != current:
                    updated_config[key] = candidate
                    changed_keys.add(key)

            if changed_keys:
                atomic_write_json(CONFIG_FILE, updated_config)

        normalized = _normalize_config(updated_config)
        self._last_notified_config = normalized

        if changed_keys:
            self._notify_listeners(normalized, changed_keys)

        return normalized, changed_keys

    def refresh_if_changed(self):
        config = self.load()
        if self._last_notified_config != config:
            changed_keys = self._diff_keys(self._last_notified_config, config)
            self._last_notified_config = config
            self._notify_listeners(config, changed_keys)
        return config

    def subscribe(self, callback):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def unsubscribe(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self, config, changed_keys):
        for callback in list(self._listeners):
            try:
                callback(config, changed_keys)
            except Exception:
                continue

    @staticmethod
    def _diff_keys(old_config, new_config):
        if old_config is None:
            return set(new_config.keys())
        changed = set()
        for key in set(old_config.keys()) | set(new_config.keys()):
            if old_config.get(key) != new_config.get(key):
                changed.add(key)
        return changed

    def save(self, key, value):
        self.set_value(key, value)

    @property
    def path(self):
        return CONFIG_FILE

    @property
    def default_config(self):
        return DEFAULT_CONFIG.copy()
