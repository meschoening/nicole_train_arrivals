import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "api_key": ""
}


def load_config():
    """
    Load configuration from JSON file.
    
    Returns:
        dict: Configuration dictionary with defaults if file doesn't exist.
    """
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        # Merge with defaults to ensure all keys exist
        return {**DEFAULT_CONFIG, **config}
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(key, value):
    """
    Update a specific config value and save to file.
    
    Args:
        key: The config key to update.
        value: The new value for the key.
    """
    config = load_config()
    config[key] = value
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

