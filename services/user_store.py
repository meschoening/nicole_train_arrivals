import hashlib
import json
import os
import re
import secrets
from datetime import datetime

from services.file_store import atomic_write_json, file_lock

USERS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "users.json"))
HASH_ITERATIONS = 200_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
PASSWORD_MIN_LENGTH = 8
DEFAULT_PREFERENCES = {
    "theme": "light",
    "sidebar_side": "left",
    "sidebar_collapsed": False,
    "avatar_data_url": "",
}


def _now_iso():
    return datetime.utcnow().isoformat() + "Z"


def _normalize_username(username):
    if username is None:
        return ""
    return username.strip().lower()


def _hash_password(password, salt=None, iterations=HASH_ITERATIONS):
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {
        "algo": "pbkdf2_sha256",
        "iterations": iterations,
        "salt": salt.hex(),
        "hash": digest.hex(),
    }


def _verify_password(password, password_record):
    if not password_record:
        return False
    if password_record.get("algo") != "pbkdf2_sha256":
        return False
    salt_hex = password_record.get("salt", "")
    hash_hex = password_record.get("hash", "")
    iterations = int(password_record.get("iterations", 0) or 0)
    if not salt_hex or not hash_hex or iterations <= 0:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(hash_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(candidate, expected)


def _validate_username(username):
    if not username:
        return False, "Username is required."
    if not USERNAME_PATTERN.match(username):
        return False, "Username must be 3-32 characters (letters, numbers, ., -, _)."
    return True, ""


def _validate_password(password):
    if password is None or password == "":
        return False, "Password is required."
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    return True, ""


def _coerce_preferences(preferences):
    if not isinstance(preferences, dict):
        preferences = {}
    theme = preferences.get("theme", DEFAULT_PREFERENCES["theme"])
    if theme not in ("light", "dark"):
        theme = DEFAULT_PREFERENCES["theme"]
    sidebar_side = preferences.get("sidebar_side", DEFAULT_PREFERENCES["sidebar_side"])
    if sidebar_side not in ("left", "right"):
        sidebar_side = DEFAULT_PREFERENCES["sidebar_side"]
    sidebar_collapsed = preferences.get("sidebar_collapsed", DEFAULT_PREFERENCES["sidebar_collapsed"])
    if isinstance(sidebar_collapsed, str):
        sidebar_collapsed = sidebar_collapsed.strip().lower() == "true"
    if not isinstance(sidebar_collapsed, bool):
        sidebar_collapsed = DEFAULT_PREFERENCES["sidebar_collapsed"]
    avatar_data_url = preferences.get("avatar_data_url", DEFAULT_PREFERENCES["avatar_data_url"])
    if not isinstance(avatar_data_url, str):
        avatar_data_url = DEFAULT_PREFERENCES["avatar_data_url"]
    return {
        "theme": theme,
        "sidebar_side": sidebar_side,
        "sidebar_collapsed": sidebar_collapsed,
        "avatar_data_url": avatar_data_url,
    }


class UserStore:
    def _read_users_raw(self):
        if not os.path.exists(USERS_FILE):
            return {"users": []}
        try:
            with open(USERS_FILE, "r") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return {"users": []}
            users = data.get("users", [])
            if not isinstance(users, list):
                users = []
            return {"users": users}
        except Exception:
            return {"users": []}

    def _write_users_raw(self, data):
        lock_path = f"{USERS_FILE}.lock"
        with file_lock(lock_path):
            atomic_write_json(USERS_FILE, data)

    def ensure_default_user(self):
        lock_path = f"{USERS_FILE}.lock"
        with file_lock(lock_path):
            data = self._read_users_raw()
            users = data.get("users", [])
            if users:
                return None

            username = "admin"
            password = secrets.token_urlsafe(12)
            record = {
                "username": username,
                "password": _hash_password(password),
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "must_change_password": True,
                "preferences": DEFAULT_PREFERENCES.copy(),
            }
            data["users"] = [record]
            atomic_write_json(USERS_FILE, data)
            return {"username": username, "password": password}

    def list_users(self):
        data = self._read_users_raw()
        users = []
        for user in data.get("users", []):
            username = user.get("username", "")
            if not username:
                continue
            users.append({
                "username": username,
                "created_at": user.get("created_at", ""),
                "updated_at": user.get("updated_at", ""),
                "must_change_password": bool(user.get("must_change_password", False)),
            })
        return sorted(users, key=lambda u: u["username"])

    def get_user(self, username):
        normalized = _normalize_username(username)
        data = self._read_users_raw()
        for user in data.get("users", []):
            if _normalize_username(user.get("username", "")) == normalized:
                return user
        return None

    def verify_user(self, username, password):
        user = self.get_user(username)
        if not user:
            return None
        if _verify_password(password, user.get("password", {})):
            return user
        return None

    def add_user(self, username, password):
        normalized = _normalize_username(username)
        valid_username, username_error = _validate_username(normalized)
        if not valid_username:
            return False, username_error
        valid_password, password_error = _validate_password(password)
        if not valid_password:
            return False, password_error

        lock_path = f"{USERS_FILE}.lock"
        with file_lock(lock_path):
            data = self._read_users_raw()
            users = data.get("users", [])
            for existing in users:
                if _normalize_username(existing.get("username", "")) == normalized:
                    return False, "Username already exists."
            record = {
                "username": normalized,
                "password": _hash_password(password),
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "must_change_password": False,
                "preferences": DEFAULT_PREFERENCES.copy(),
            }
            users.append(record)
            data["users"] = users
            atomic_write_json(USERS_FILE, data)
        return True, ""

    def set_password(self, username, password):
        normalized = _normalize_username(username)
        valid_password, password_error = _validate_password(password)
        if not valid_password:
            return False, password_error

        lock_path = f"{USERS_FILE}.lock"
        with file_lock(lock_path):
            data = self._read_users_raw()
            users = data.get("users", [])
            for user in users:
                if _normalize_username(user.get("username", "")) == normalized:
                    user["password"] = _hash_password(password)
                    user["updated_at"] = _now_iso()
                    user["must_change_password"] = False
                    atomic_write_json(USERS_FILE, data)
                    return True, ""
        return False, "User not found."

    def remove_user(self, username):
        normalized = _normalize_username(username)
        lock_path = f"{USERS_FILE}.lock"
        with file_lock(lock_path):
            data = self._read_users_raw()
            users = data.get("users", [])
            remaining = [user for user in users if _normalize_username(user.get("username", "")) != normalized]
            if len(remaining) == len(users):
                return False, "User not found."
            if len(remaining) == 0:
                return False, "At least one user must remain."
            data["users"] = remaining
            atomic_write_json(USERS_FILE, data)
        return True, ""

    def get_preferences(self, username):
        user = self.get_user(username)
        if not user:
            return DEFAULT_PREFERENCES.copy()
        return _coerce_preferences(user.get("preferences", {}))

    def update_preferences(self, username, updates):
        if not isinstance(updates, dict) or not updates:
            return False, "No updates provided.", DEFAULT_PREFERENCES.copy()
        normalized = _normalize_username(username)
        lock_path = f"{USERS_FILE}.lock"
        with file_lock(lock_path):
            data = self._read_users_raw()
            users = data.get("users", [])
            for user in users:
                if _normalize_username(user.get("username", "")) != normalized:
                    continue
                preferences = _coerce_preferences(user.get("preferences", {}))
                if "theme" in updates:
                    preferences["theme"] = updates.get("theme")
                if "sidebar_side" in updates:
                    preferences["sidebar_side"] = updates.get("sidebar_side")
                if "sidebar_collapsed" in updates:
                    preferences["sidebar_collapsed"] = updates.get("sidebar_collapsed")
                if "avatar_data_url" in updates:
                    preferences["avatar_data_url"] = updates.get("avatar_data_url")
                user["preferences"] = _coerce_preferences(preferences)
                user["updated_at"] = _now_iso()
                data["users"] = users
                atomic_write_json(USERS_FILE, data)
                return True, "", user["preferences"]
        return False, "User not found.", DEFAULT_PREFERENCES.copy()
