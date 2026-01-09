"""Config access wrapper for dependency injection."""

import config_handler


class ConfigStore:
    """Provides load/save access to config data."""

    def __init__(self, handler=None):
        self._handler = handler or config_handler

    def load(self):
        return self._handler.load_config()

    def save(self, key, value):
        self._handler.save_config(key, value)

    @property
    def path(self):
        return self._handler.CONFIG_FILE
