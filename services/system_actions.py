"""Shared system command runner with consistent logging and errors."""

from dataclasses import dataclass
import logging
import shlex
import subprocess
import time
from typing import Mapping, Optional, Sequence


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    command: Sequence[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool
    error: Optional[str] = None

    @property
    def ok(self):
        return self.returncode == 0 and not self.timed_out and not self.error


class CommandError(Exception):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


def format_command(command):
    try:
        return shlex.join(command)
    except TypeError:
        return " ".join(str(part) for part in command)


def truncate_output(value, limit=400):
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...({len(value) - limit} more chars)"


def run_command(
    command,
    timeout_s,
    cwd=None,
    env: Optional[Mapping[str, str]] = None,
    check=False,
    log_label=None,
):
    label = log_label or "system_command"
    formatted = format_command(command)
    logger.info(
        "Command start label=%s command=%s timeout_s=%s cwd=%s",
        label,
        formatted,
        timeout_s,
        cwd or "",
    )
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        duration = time.monotonic() - started
        result = CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_s=duration,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        result = CommandResult(
            command=command,
            returncode=-1,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            duration_s=duration,
            timed_out=True,
            error="timeout",
        )
    except Exception as exc:
        duration = time.monotonic() - started
        result = CommandResult(
            command=command,
            returncode=-1,
            stdout="",
            stderr="",
            duration_s=duration,
            timed_out=False,
            error=str(exc),
        )

    log_level = logging.INFO if result.ok else logging.WARNING
    logger.log(
        log_level,
        "Command done label=%s rc=%s timeout=%s duration_s=%.2f error=%s stdout=%s stderr=%s",
        label,
        result.returncode,
        result.timed_out,
        result.duration_s,
        result.error or "",
        truncate_output(result.stdout),
        truncate_output(result.stderr),
    )

    if check and not result.ok:
        raise CommandError(f"Command failed: {formatted}", result)

    return result


def start_process(
    command,
    cwd=None,
    env: Optional[Mapping[str, str]] = None,
    log_label=None,
    timeout_s=None,
    **kwargs,
):
    label = log_label or "system_process"
    formatted = format_command(command)
    logger.info(
        "Process start label=%s command=%s timeout_s=%s cwd=%s",
        label,
        formatted,
        timeout_s,
        cwd or "",
    )
    try:
        return subprocess.Popen(command, cwd=cwd, env=env, **kwargs)
    except Exception as exc:
        result = CommandResult(
            command=command,
            returncode=-1,
            stdout="",
            stderr="",
            duration_s=0.0,
            timed_out=False,
            error=str(exc),
        )
        logger.error(
            "Process start failed label=%s error=%s",
            label,
            result.error,
        )
        raise CommandError(f"Failed to start process: {formatted}", result) from exc
