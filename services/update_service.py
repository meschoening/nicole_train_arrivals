"""Git update workflow used by the UI."""

import os
import time

from PyQt5.QtCore import QObject, QProcess, pyqtSignal
from PyQt5.QtWidgets import QApplication

from services.config_store import load_config
from services.system_actions import run_command, start_process


_GIT_DEBUG = True


def has_git_error(output_text):
    if not output_text:
        return False
    lower = output_text.lower()
    for token in ("error:", "fatal:", "could not", "failed to", "permission denied", "cannot"):
        if token in lower:
            return True
    return False


def has_updates(output_text):
    if not output_text:
        return False
    lower = output_text.lower()
    if "already up to date" in lower or "already up-to-date" in lower:
        return False
    for token in ("updating", "fast-forward", "files changed", "file changed", "insertions", "deletions"):
        if token in lower:
            return True
    if "error" not in lower and "fatal" not in lower:
        lines = [ln.strip() for ln in output_text.split("\n") if ln.strip()]
        substantial = [ln for ln in lines if not ln.startswith("From") and not ln.startswith("remote:")]
        if len(substantial) > 1:
            return True
    return False


def build_git_command(args, git_user=None):
    if git_user:
        return ["sudo", "-u", git_user, "git"] + list(args)
    return ["git"] + list(args)


def run_git_command(args, cwd, git_user=None, timeout=5):
    return run_command(
        build_git_command(args, git_user=git_user),
        cwd=cwd,
        timeout_s=timeout,
        log_label="git_command",
    )


def popen_git_command(args, cwd, git_user=None, **kwargs):
    return start_process(
        build_git_command(args, git_user=git_user),
        cwd=cwd,
        log_label="git_process",
        timeout_s=None,
        **kwargs,
    )


def get_latest_commit_message(working_dir, git_user=None):
    try:
        result = run_git_command(
            ["log", "-1", "--format=%s"],
            cwd=working_dir,
            git_user=git_user,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_git_heads(working_dir, git_user=None, branches=None, branch=None, timeout=5):
    """Get the local HEAD and remote HEAD for comparison.
    
    Args:
        working_dir: Git repository directory
        git_user: Optional user to run git commands as
        branches: List of branches to try (legacy, for fallback)
        branch: Single branch name to check (e.g., "main"). If provided, checks origin/<branch>
        timeout: Command timeout in seconds
    
    Returns:
        Tuple of (local_head, remote_head) commit hashes, or (None, None) on error
    """
    # If a single branch is specified, use it; otherwise fall back to the branches list
    if branch is not None:
        branches_to_check = [f"origin/{branch}"]
    elif branches is not None:
        branches_to_check = branches
    else:
        branches_to_check = ["origin/main", "origin/master"]

    local_result = run_git_command(
        ["rev-parse", "HEAD"],
        cwd=working_dir,
        git_user=git_user,
        timeout=timeout,
    )
    if local_result.returncode != 0:
        return None, None
    local_head = local_result.stdout.strip()

    remote_head = None
    for branch_ref in branches_to_check:
        remote_result = run_git_command(
            ["rev-parse", branch_ref],
            cwd=working_dir,
            git_user=git_user,
            timeout=timeout,
        )
        if remote_result.returncode == 0:
            remote_head = remote_result.stdout.strip()
            break

    return local_head, remote_head


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

    def log(self, message):
        """Log git operation debug info with timestamp."""
        if _GIT_DEBUG:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            flag_state = self.settings_server.is_git_operation_in_progress()
            print(f"[GIT-DEBUG {timestamp}] [update_service] [flag={flag_state}] {message}", flush=True)

    def wait_for_fetch_if_running(self):
        """Wait for any running background git fetch to complete before proceeding."""
        self.log("wait_for_fetch_if_running: Checking for running git operations...")
        if self.git_fetch_process is not None and self.git_fetch_process.state() == QProcess.Running:
            self.log("wait_for_fetch_if_running: Local git_fetch_process is running, waiting...")
            self.pull_output.emit("Waiting for background update check to finish...\n")
            self.git_fetch_process.waitForFinished(10000)
            self.log("wait_for_fetch_if_running: Local git_fetch_process finished")

        if self.settings_server.is_git_operation_in_progress():
            self.log("wait_for_fetch_if_running: Web server git operation in progress, polling...")
            self.pull_output.emit("Waiting for web server git operation to finish...\n")
            for i in range(100):
                if not self.settings_server.is_git_operation_in_progress():
                    self.log(
                        f"wait_for_fetch_if_running: Web server git operation finished after {i} polls"
                    )
                    break
                if self._process_events:
                    self._process_events()
                time.sleep(0.1)
            else:
                self.log("wait_for_fetch_if_running: Timeout waiting for web server git operation!")
        self.log("wait_for_fetch_if_running: Done checking, proceeding...")

    def run_pull(self):
        """Start the git pull process."""
        self.log("run_git_pull: Starting...")
        self.wait_for_fetch_if_running()

        if not self.settings_server.try_start_git_operation(caller="update_service_run_pull"):
            self.log("run_git_pull: Skipping - git operation already in progress")
            self.pull_output.emit("Another update is already in progress.\n")
            self.pull_finished.emit({
                "exit_code": -1,
                "has_error": True,
                "has_updates": False,
                "commit_message": None,
                "reason": "busy",
            })
            return

        self.git_output = ""
        self.git_process = QProcess()
        self.git_process.setWorkingDirectory(self.working_dir)
        self.git_process.readyReadStandardOutput.connect(self.on_git_output_ready)
        self.git_process.readyReadStandardError.connect(self.on_git_output_ready)
        self.git_process.errorOccurred.connect(self.on_git_error)
        self.git_process.finished.connect(self.on_git_finished)

        self.log("run_git_pull: Starting 'git pull' via QProcess")
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
            self.log("check_for_git_updates: Skipping - local git_fetch_process still running")
            return

        if not self.settings_server.try_start_git_operation(caller="update_service_check_for_updates"):
            self.log("check_for_git_updates: Skipping - git operation already in progress")
            return

        self.log("check_for_git_updates: Starting background git fetch")

        self.git_fetch_process = QProcess()
        self.git_fetch_process.setWorkingDirectory(self.working_dir)
        self.git_fetch_process.errorOccurred.connect(self.on_git_fetch_error)
        self.git_fetch_process.finished.connect(self.on_git_fetch_finished)

        self.log("check_for_git_updates: Starting 'git fetch' via QProcess")
        self.git_fetch_process.start("git", ["fetch"])

    def on_git_output_ready(self):
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

    def on_git_finished(self, exit_code, exit_status):
        self.log(f"on_git_finished: exit_code={exit_code}, exit_status={exit_status}")
        preview = self.git_output[:500] if self.git_output else "(empty)"
        self.log(f"on_git_finished: git_output={preview}")
        self.log("on_git_finished: Releasing git operation")
        self.settings_server.finish_git_operation(caller="update_service_run_pull")

        self.pull_output.emit(f"\nProcess finished with exit code: {exit_code}")

        has_error = exit_code != 0 or has_git_error(self.git_output)
        updates_found = False
        commit_message = None

        if not has_error:
            updates_found = has_updates(self.git_output)
            if updates_found:
                commit_message = get_latest_commit_message(self.working_dir)

        if updates_found or (not has_error):
            if self.update_available:
                self.update_available = False
                self.update_available_changed.emit(False)

        result = {
            "exit_code": exit_code,
            "has_error": has_error,
            "has_updates": updates_found,
            "commit_message": commit_message,
        }
        self.pull_finished.emit(result)

    def on_git_fetch_finished(self, exit_code, exit_status):
        self.log(f"on_git_fetch_finished: exit_code={exit_code}, exit_status={exit_status}")
        self.log("on_git_fetch_finished: Releasing git operation")
        self.settings_server.finish_git_operation(caller="update_service_check_for_updates")

        if exit_code != 0:
            self.log(f"on_git_fetch_finished: Fetch failed with exit_code={exit_code}")
            return

        try:
            # Use configured branch for update check
            config = load_config()
            configured_branch = config.get("git_branch", "main")
            local_head, remote_head = get_git_heads(self.working_dir, branch=configured_branch)
            if not local_head or not remote_head:
                return

            if local_head != remote_head and not self.update_available:
                self.update_available = True
                self.update_available_changed.emit(True)
            elif local_head == remote_head and self.update_available:
                self.update_available = False
                self.update_available_changed.emit(False)
        except Exception:
            pass

    def on_git_error(self, error):
        self.log(f"on_git_error: error={error}")
        if error == QProcess.FailedToStart:
            self.settings_server.finish_git_operation(caller="update_service_run_pull")
            self.pull_output.emit("Git pull failed to start.\n")
            self.pull_finished.emit({
                "exit_code": -1,
                "has_error": True,
                "has_updates": False,
                "commit_message": None,
            })

    def on_git_fetch_error(self, error):
        self.log(f"on_git_fetch_error: error={error}")
        if error == QProcess.FailedToStart:
            self.settings_server.finish_git_operation(caller="update_service_check_for_updates")


class UpdateServiceRunner:
    """Runs git update commands for non-Qt environments."""

    def __init__(self, working_dir=None, git_user=None):
        self.working_dir = working_dir or os.getcwd()
        self.git_user = git_user

    def popen_pull(self, **kwargs):
        return popen_git_command(
            ["pull"],
            cwd=self.working_dir,
            git_user=self.git_user,
            **kwargs,
        )

    def fetch(self, timeout=30):
        return run_git_command(
            ["fetch"],
            cwd=self.working_dir,
            git_user=None,
            timeout=timeout,
        )

    def get_heads(self, timeout=10, branch=None):
        return get_git_heads(
            self.working_dir,
            git_user=None,
            branch=branch,
            timeout=timeout,
        )

    def get_remote_branches(self, timeout=10):
        """Get list of remote branches from git."""
        fetch_result = run_git_command(
            ["fetch", "--prune"],
            cwd=self.working_dir,
            git_user=self.git_user,
            timeout=timeout,
        )
        if fetch_result.returncode != 0:
            return []
        result = run_git_command(
            ["branch", "-r"],
            cwd=self.working_dir,
            git_user=self.git_user,
            timeout=timeout,
        )
        if result.returncode != 0:
            return []
        
        branches = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            # Skip HEAD pointer lines like "origin/HEAD -> origin/main"
            if "->" in line:
                continue
            # Remove "origin/" prefix
            if line.startswith("origin/"):
                branch_name = line[7:]  # Remove "origin/" prefix
                branches.append(branch_name)
        return sorted(branches)

    def get_current_branch(self, timeout=5):
        """Get the current local branch name."""
        result = run_git_command(
            ["branch", "--show-current"],
            cwd=self.working_dir,
            git_user=self.git_user,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def switch_branch(self, branch, timeout=60):
        """Switch to a different branch (git fetch + git checkout)."""
        # First fetch to ensure we have latest refs
        fetch_result = run_git_command(
            ["fetch", "--all"],
            cwd=self.working_dir,
            git_user=self.git_user,
            timeout=timeout,
        )
        if fetch_result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to fetch: {fetch_result.stderr.strip()}",
            }
        
        # Checkout the branch
        checkout_result = run_git_command(
            ["checkout", branch],
            cwd=self.working_dir,
            git_user=self.git_user,
            timeout=timeout,
        )
        if checkout_result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to checkout: {checkout_result.stderr.strip()}",
            }
        
        return {
            "success": True,
            "branch": branch,
            "message": checkout_result.stdout.strip() or checkout_result.stderr.strip(),
        }

    def get_latest_commit_message(self):
        return get_latest_commit_message(self.working_dir, git_user=self.git_user)

    def check_for_updates(self, fetch_timeout=30, head_timeout=10):
        fetch_result = self.fetch(timeout=fetch_timeout)
        if fetch_result.returncode != 0:
            return {
                "updates_available": False,
                "error": "Failed to fetch from remote",
            }

        local_head, remote_head = self.get_heads(timeout=head_timeout)
        if not local_head or not remote_head:
            return {
                "updates_available": False,
                "error": "Could not determine remote branch",
            }

        return {
            "updates_available": local_head != remote_head,
            "local_head": local_head,
            "remote_head": remote_head,
        }
