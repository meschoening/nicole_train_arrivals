import json
import os

from services.file_store import atomic_write_json, file_lock

MESSAGES_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "messages.json"))

DEFAULT_MESSAGES = {
    "messages": [
        {"text": "Have a great day!", "color": None},
        {"text": "Love you!", "color": None},
    ],
    "timing_mode": "periodic",
    "periodic_interval_minutes": 30,
    "periodic_time_window_enabled": False,
    "periodic_window_start": "09:00",
    "periodic_window_end": "17:00",
    "random_min_minutes": 15,
    "random_max_minutes": 60,
    "random_time_window_enabled": False,
    "random_window_start": "09:00",
    "random_window_end": "17:00",
    "display_duration_seconds": 5,
    "fade_duration_ms": 800,
}


def load_messages():
    """Load message configuration from JSON file."""
    if not os.path.exists(MESSAGES_FILE):
        save_messages(DEFAULT_MESSAGES.copy())
        return DEFAULT_MESSAGES.copy()

    try:
        with open(MESSAGES_FILE, "r") as f:
            data = json.load(f)

        messages_list = data.get("messages", [])
        if messages_list and isinstance(messages_list[0], str):
            data["messages"] = [{"text": msg, "color": None} for msg in messages_list]
            save_messages(data)

        result = {**DEFAULT_MESSAGES, **data}

        if "messages" in result:
            migrated_messages = []
            for msg in result["messages"]:
                if isinstance(msg, str):
                    migrated_messages.append({"text": msg, "color": None})
                elif isinstance(msg, dict):
                    migrated_msg = {"text": msg.get("text", ""), "color": msg.get("color")}
                    migrated_messages.append(migrated_msg)
            result["messages"] = migrated_messages

        return result
    except (json.JSONDecodeError, IOError):
        save_messages(DEFAULT_MESSAGES.copy())
        return DEFAULT_MESSAGES.copy()


def save_messages(data):
    """Save message configuration to JSON file."""
    lock_path = f"{MESSAGES_FILE}.lock"
    with file_lock(lock_path):
        atomic_write_json(MESSAGES_FILE, data)


class MessageStore:
    """Provides load/save access to message data."""

    def load(self):
        return load_messages()

    def save(self, data):
        save_messages(data)

    @property
    def path(self):
        return MESSAGES_FILE
