"""Shared coordination for background jobs and cross-thread signals."""

from contextlib import contextmanager
import threading

try:
    from PyQt5.QtCore import QObject, pyqtSignal
except ImportError:  # pragma: no cover - optional for headless server use
    QObject = None
    pyqtSignal = None


if QObject is not None:
    class BackgroundJobSignals(QObject):
        message_triggered = pyqtSignal(object)
        settings_changed = pyqtSignal()
        git_operation_changed = pyqtSignal(bool)
else:
    class BackgroundJobSignals:
        def __init__(self):
            pass


class BackgroundJobCoordinator:
    """Centralizes background job state and coordination."""

    def __init__(self):
        self._state_lock = threading.Lock()
        self._git_lock = threading.Lock()
        self._git_lock_held = False
        self._git_active = False
        self._message_pending = False
        self._message_value = None
        self._settings_changed_pending = False
        self._signals = BackgroundJobSignals() if QObject is not None else None

    @property
    def signals(self):
        return self._signals

    def trigger_message(self, message):
        with self._state_lock:
            self._message_pending = True
            self._message_value = message
        if self._signals:
            self._signals.message_triggered.emit(message)

    def consume_message_trigger(self):
        with self._state_lock:
            if self._message_pending:
                message = self._message_value
                self._message_pending = False
                self._message_value = None
                return message
            return False

    def mark_settings_changed(self):
        with self._state_lock:
            self._settings_changed_pending = True
        if self._signals:
            self._signals.settings_changed.emit()

    def consume_settings_changed(self):
        with self._state_lock:
            if self._settings_changed_pending:
                self._settings_changed_pending = False
                return True
            return False

    def is_git_operation_in_progress(self):
        with self._state_lock:
            return self._git_active

    def set_git_operation_in_progress(self, active, caller="unknown"):
        with self._state_lock:
            self._git_active = active
        if self._signals:
            self._signals.git_operation_changed.emit(active)

    def try_start_git_operation(self, caller="unknown"):
        if not self._git_lock.acquire(blocking=False):
            return False
        with self._state_lock:
            self._git_lock_held = True
        self.set_git_operation_in_progress(True, caller=caller)
        return True

    def finish_git_operation(self, caller="unknown"):
        should_release = False
        with self._state_lock:
            if self._git_lock_held:
                self._git_lock_held = False
                should_release = True
        self.set_git_operation_in_progress(False, caller=caller)
        if should_release:
            self._git_lock.release()

    @contextmanager
    def git_operation(self, caller="unknown"):
        self._git_lock.acquire()
        with self._state_lock:
            self._git_lock_held = True
        self.set_git_operation_in_progress(True, caller=caller)
        try:
            yield
        finally:
            self.finish_git_operation(caller=caller)


background_jobs = BackgroundJobCoordinator()
