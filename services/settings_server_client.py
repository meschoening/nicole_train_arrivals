"""Wrapper for the embedded web settings server."""

import web_settings_server


class SettingsServerClient:
    """Exposes web settings server state for the UI layer."""

    def __init__(self, server=None):
        self._server = server or web_settings_server

    def start(self, data_handler, host="0.0.0.0", port=443):
        return self._server.start_web_settings_server(data_handler, host=host, port=port)

    def get_pending_message_trigger(self):
        return self._server.get_pending_message_trigger()

    def get_pending_settings_change(self):
        return self._server.get_pending_settings_change()

    def is_git_operation_in_progress(self):
        return self._server.is_git_operation_in_progress()

    def set_git_operation_in_progress(self, active, caller="unknown"):
        return self._server.set_git_operation_in_progress(active, caller=caller)
