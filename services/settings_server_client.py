"""Wrapper for the embedded web settings server."""

import web_settings_server

from services.background_jobs import background_jobs


class SettingsServerClient:
    """Exposes web settings server state for the UI layer."""

    def __init__(self, server=None, jobs=None):
        self._server = server or web_settings_server
        self._background_jobs = jobs or background_jobs

    def start(self, data_handler, host="0.0.0.0", port=443):
        return self._server.start_web_settings_server(data_handler, host=host, port=port)

    @property
    def signals(self):
        return self._background_jobs.signals

    def get_pending_message_trigger(self):
        return self._background_jobs.consume_message_trigger()

    def get_pending_settings_change(self):
        return self._background_jobs.consume_settings_changed()

    def is_git_operation_in_progress(self):
        return self._background_jobs.is_git_operation_in_progress()

    def set_git_operation_in_progress(self, active, caller="unknown"):
        return self._background_jobs.set_git_operation_in_progress(active, caller=caller)

    def try_start_git_operation(self, caller="unknown"):
        return self._background_jobs.try_start_git_operation(caller=caller)

    def finish_git_operation(self, caller="unknown"):
        return self._background_jobs.finish_git_operation(caller=caller)
