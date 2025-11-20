import json
import os

MESSAGES_FILE = "messages.json"

DEFAULT_MESSAGES = {
    "messages": [
        "Have a great day!",
        "Love you!"
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
    "fade_duration_ms": 800
}


def load_messages():
    """
    Load message configuration from JSON file.
    Creates the file with default settings if it doesn't exist.
    
    Returns:
        dict: Message configuration dictionary with defaults if file doesn't exist.
    """
    if not os.path.exists(MESSAGES_FILE):
        save_messages(DEFAULT_MESSAGES.copy())
        return DEFAULT_MESSAGES.copy()
    
    try:
        with open(MESSAGES_FILE, 'r') as f:
            data = json.load(f)
        # Merge with defaults to ensure all keys exist
        return {**DEFAULT_MESSAGES, **data}
    except (json.JSONDecodeError, IOError):
        save_messages(DEFAULT_MESSAGES.copy())
        return DEFAULT_MESSAGES.copy()


def save_messages(data):
    """
    Save message configuration to JSON file.
    
    Args:
        data: Dictionary containing message configuration to save.
    """
    with open(MESSAGES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

