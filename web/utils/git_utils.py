"""Git operation utilities for the web server."""

import traceback
from datetime import datetime

from services.background_jobs import background_jobs


# Debug logging for git operations
GIT_DEBUG = True


def git_debug_log(message, include_stack=False):
    """Log git operation debug info with timestamp."""
    if GIT_DEBUG:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        flag_state = background_jobs.is_git_operation_in_progress()
        print(
            f"[GIT-DEBUG {timestamp}] [web_server] [flag={flag_state}] {message}",
            flush=True,
        )
        if include_stack:
            print(f"[GIT-DEBUG {timestamp}] Stack trace:", flush=True)
            traceback.print_stack()


def is_git_operation_in_progress():
    """Check if a git operation is currently in progress."""
    result = background_jobs.is_git_operation_in_progress()
    if GIT_DEBUG:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(
            f"[GIT-DEBUG {timestamp}] [web_server] is_git_operation_in_progress() -> {result}",
            flush=True,
        )
    return result


def set_git_operation_in_progress(active, caller="unknown"):
    """Set the git operation in progress flag."""
    if GIT_DEBUG:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(
            f"[GIT-DEBUG {timestamp}] [web_server] set_git_operation_in_progress({active}) called by {caller}",
            flush=True,
        )
    background_jobs.set_git_operation_in_progress(active, caller=caller)


def get_boot_id():
    """Get the current boot ID from the system.

    Returns:
        str or None: Boot ID string or None if unavailable
    """
    try:
        with open("/proc/sys/kernel/random/boot_id", "r") as handle:
            return handle.read().strip()
    except Exception:
        return None


def clear_update_state(config_store):
    """Clear all update-related state from config."""
    config_store.set_values(
        {
            "update_requires_reboot": False,
            "update_console_output": "",
            "update_commit_message": "",
            "update_boot_id": "",
        }
    )


def persist_update_state(config_store, console_output, commit_message=""):
    """Persist update state to config after a successful update."""
    updates = {
        "update_requires_reboot": True,
        "update_console_output": console_output or "",
        "update_commit_message": commit_message or "",
        "update_boot_id": get_boot_id() or "",
    }
    config_store.set_values(updates)


def clear_update_state_if_rebooted(config_store):
    """Clear update state if the system has rebooted since the update."""
    if not config_store.get_bool("update_requires_reboot", False):
        if config_store.get_str("update_boot_id", ""):
            config_store.set_value("update_boot_id", "")
        return

    current_boot_id = get_boot_id()
    if not current_boot_id:
        return

    stored_boot_id = config_store.get_str("update_boot_id", "")
    if stored_boot_id and stored_boot_id != current_boot_id:
        clear_update_state(config_store)
    elif not stored_boot_id:
        config_store.set_value("update_boot_id", current_boot_id)


def get_saved_update_state(config_store):
    """Get the saved update state from config.

    Returns:
        dict: Update state with reboot_required, console_output, commit_message
    """
    return {
        "reboot_required": config_store.get_bool("update_requires_reboot", False),
        "console_output": config_store.get_str("update_console_output", ""),
        "commit_message": config_store.get_str("update_commit_message", ""),
    }
