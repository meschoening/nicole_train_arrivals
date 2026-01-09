"""Git update workflow used by the UI."""

import os
import subprocess
import time

from PyQt5.QtCore import QObject, QProcess, pyqtSignal
from PyQt5.QtWidgets import QApplication


_GIT_DEBUG = True


class UpdateService(QObject):
    """Runs git pull/fetch operations and reports results via signals."""

    pull_output = pyqtSignal(str)
    pull_finished = pyqtSignal(object)
    update_available_changed = pyqtSignal(bool)

    def __init__(self, settings_server, working_dir=None, process_events=None, parent=None):
        super().__init__(parent)
        self.settings_server = settings_server
        self.working_dir = working_dir or os.getcwd()
        self._process_events = process_events or QApplication.processEvents
        self.git_process = None
        self.git_fetch_process = None
        self.git_output = ""
        self.update_available = False

    def _log(self, message):
        """Log git operation debug info with timestamp."""
        if _GIT_DEBUG:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            flag_state = self.settings_server.is_git_operation_in_progress()
            print(f"[GIT-DEBUG {timestamp}] [update_service] [flag={flag_state}] {message}", flush=True)

    def wait_for_fetch_if_running(self):
        """Wait for any running background git fetch to complete before proceeding."""
        self._log("wait_for_fetch_if_running: Checking for running git operations...")
        if self.git_fetch_process is not None and self.git_fetch_process.state() == QProcess.Running:
            self._log("wait_for_fetch_if_running: Local git_fetch_process is running, waiting...")
            self.pull_output.emit("Waiting for background update check to finish...\n")
            self.git_fetch_process.waitForFinished(10000)
            self._log("wait_for_fetch_if_running: Local git_fetch_process finished")

        if self.settings_server.is_git_operation_in_progress():
            self._log("wait_for_fetch_if_running: Web server git operation in progress, polling...")
            self.pull_output.emit("Waiting for web server git operation to finish...\n")
            for i in range(100):
                if not self.settings_server.is_git_operation_in_progress():
                    self._log(
                        f"wait_for_fetch_if_running: Web server git operation finished after {i} polls"
                    )
                    break
                if self._process_events:
                    self._process_events()
                time.sleep(0.1)
            else:
                self._log("wait_for_fetch_if_running: Timeout waiting for web server git operation!")
        self._log("wait_for_fetch_if_running: Done checking, proceeding...")

    def run_pull(self):
        """Start the git pull process."""
        self._log("run_git_pull: Starting...")
        self.wait_for_fetch_if_running()

        self._log("run_git_pull: Setting flag to True")
        self.settings_server.set_git_operation_in_progress(True)

        self.git_output = ""
        self.git_process = QProcess()
        self.git_process.setWorkingDirectory(self.working_dir)
        self.git_process.readyReadStandardOutput.connect(self._on_git_output_ready)
        self.git_process.readyReadStandardError.connect(self._on_git_output_ready)
        self.git_process.finished.connect(self._on_git_finished)

        self._log("run_git_pull: Starting 'git pull' via QProcess")
        self.pull_output.emit("Running git pull...\n")
        self.git_process.start("git", ["pull"])

    def cancel_pull(self):
        """Stop an in-progress git pull if one is running."""
        if self.git_process is not None and self.git_process.state() == QProcess.Running:
            self.git_process.kill()
            self.git_process.waitForFinished()

    def check_for_updates(self):
        """Check for available git updates in the background (non-destructive)."""
        if self.git_fetch_process is not None and self.git_fetch_process.state() == QProcess.Running:
            self._log("check_for_git_updates: Skipping - local git_fetch_process still running")
            return

        if self.settings_server.is_git_operation_in_progress():
            self._log("check_for_git_updates: Skipping - web server git operation in progress")
            return

        self._log("check_for_git_updates: Starting background git fetch")
        self.settings_server.set_git_operation_in_progress(True)

        self.git_fetch_process = QProcess()
        self.git_fetch_process.setWorkingDirectory(self.working_dir)
        self.git_fetch_process.finished.connect(self._on_git_fetch_finished)

        self._log("check_for_git_updates: Starting 'git fetch' via QProcess")
        self.git_fetch_process.start("git", ["fetch"])

    def _on_git_output_ready(self):
        if self.git_process is None:
            return

        stdout = self.git_process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        if stdout:
            self.git_output += stdout
            self.pull_output.emit(stdout.rstrip("\n"))

        stderr = self.git_process.readAllStandardError().data().decode("utf-8", errors="replace")
        if stderr:
            self.git_output += stderr
            self.pull_output.emit(stderr.rstrip("\n"))

    def _on_git_finished(self, exit_code, exit_status):
        self._log(f"on_git_finished: exit_code={exit_code}, exit_status={exit_status}")
        preview = self.git_output[:500] if self.git_output else "(empty)"
        self._log(f"on_git_finished: git_output={preview}")
        self._log("on_git_finished: Clearing flag to False")
        self.settings_server.set_git_operation_in_progress(False)

        self.pull_output.emit(f"\nProcess finished with exit code: {exit_code}")

        has_error = exit_code != 0 or self._has_git_error()
        has_updates = False
        commit_message = None

        if not has_error:
            has_updates = self._parse_git_output()
            if has_updates:
                commit_message = self._get_latest_commit_message()

        if has_updates or (not has_error):
            if self.update_available:
                self.update_available = False
                self.update_available_changed.emit(False)

        result = {
            "exit_code": exit_code,
            "has_error": has_error,
            "has_updates": has_updates,
            "commit_message": commit_message,
        }
        self.pull_finished.emit(result)

    def _has_git_error(self):
        output_lower = self.git_output.lower()
        error_indicators = [
            "error:",
            "fatal:",
            "could not",
            "failed to",
            "permission denied",
            "cannot",
        ]

        for indicator in error_indicators:
            if indicator in output_lower:
                return True

        return False

    def _parse_git_output(self):
        output_lower = self.git_output.lower()

        if "already up to date" in output_lower or "already up-to-date" in output_lower:
            return False

        update_indicators = [
            "updating",
            "fast-forward",
            "files changed",
            "file changed",
            "insertions",
            "deletions",
        ]

        for indicator in update_indicators:
            if indicator in output_lower:
                return True

        if self.git_output and "error" not in output_lower and "fatal" not in output_lower:
            lines = [line.strip() for line in self.git_output.split("\n") if line.strip()]
            substantial_lines = [
                line
                for line in lines
                if not line.startswith("From") and not line.startswith("remote:")
            ]
            if len(substantial_lines) > 1:
                return True

        return False

    def _get_latest_commit_message(self):
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%s"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _on_git_fetch_finished(self, exit_code, exit_status):
        self._log(f"on_git_fetch_finished: exit_code={exit_code}, exit_status={exit_status}")
        self._log("on_git_fetch_finished: Clearing flag to False")
        self.settings_server.set_git_operation_in_progress(False)

        if exit_code != 0:
            self._log(f"on_git_fetch_finished: Fetch failed with exit_code={exit_code}")
            return

        try:
            local_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if local_result.returncode != 0:
                return

            local_head = local_result.stdout.strip()

            remote_head = None
            for branch in ["origin/main", "origin/master"]:
                remote_result = subprocess.run(
                    ["git", "rev-parse", branch],
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if remote_result.returncode == 0:
                    remote_head = remote_result.stdout.strip()
                    break

            if remote_head is None:
                return

            if local_head != remote_head and not self.update_available:
                self.update_available = True
                self.update_available_changed.emit(True)
            elif local_head == remote_head and self.update_available:
                self.update_available = False
                self.update_available_changed.emit(False)
        except Exception:
            pass
