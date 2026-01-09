"""Message access wrapper for dependency injection."""

import message_handler


class MessageStore:
    """Provides load/save access to message data."""

    def __init__(self, handler=None):
        self._handler = handler or message_handler

    def load(self):
        return self._handler.load_messages()

    def save(self, data):
        self._handler.save_messages(data)

    @property
    def path(self):
        return self._handler.MESSAGES_FILE
