"""Flask application factory for the settings server.

This module provides a factory function for creating the Flask application.
It can be used by web_settings_server.py as a drop-in replacement for the
inline app creation, enabling the blueprint-based architecture.

Example usage:
    from web.app import create_app

    app, ssl_context = create_app(data_handler)
    app.run(host="0.0.0.0", port=443, ssl_context=ssl_context)
"""

import os
import secrets
import threading

from flask import Flask, session, request, redirect, url_for, jsonify, render_template

from services.config_store import ConfigStore
from services.message_store import MessageStore
from services.user_store import UserStore
from services.system_service import SystemService
from services.update_service import UpdateServiceRunner

from web.utils.ssl_utils import get_ssl_cert_paths
from web.utils.git_utils import clear_update_state_if_rebooted
from services.system_actions import run_command


def get_current_user():
    """Resolve the current OS username for sudo/git operations."""
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        user = os.environ.get("USER") or os.environ.get("USERNAME")
        return user if user else None


def create_app(data_handler, config_store=None):
    """Create and configure the Flask application.

    Args:
        data_handler: DataHandler instance for Metro API data
        config_store: Optional ConfigStore instance (created if not provided)

    Returns:
        tuple: (Flask app, ssl_context, ssl_enabled flag)
    """
    if config_store is None:
        config_store = ConfigStore()

    clear_update_state_if_rebooted(config_store)

    message_store = MessageStore()
    user_store = UserStore()
    system_service = SystemService()
    git_user = get_current_user()
    update_service = UpdateServiceRunner(
        working_dir=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        git_user=git_user,
    )

    # Check for SSL certificates
    ssl_context = None
    cert_path, key_path = get_ssl_cert_paths()
    ssl_enabled = cert_path is not None and key_path is not None
    if ssl_enabled:
        ssl_context = (cert_path, key_path)

    app = Flask(
        __name__,
        template_folder=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
        ),
    )

    # Configure session
    def ensure_session_secret():
        secret = config_store.get_str("web_session_secret", "")
        if not secret:
            secret = secrets.token_hex(32)
            config_store.set_value("web_session_secret", secret)
        return secret

    app.secret_key = ensure_session_secret()
    app.config.update(
        {
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            "SESSION_COOKIE_SECURE": ssl_enabled,
        }
    )

    # Store services in app config for blueprints to access
    app.config["config_store"] = config_store
    app.config["message_store"] = message_store
    app.config["user_store"] = user_store
    app.config["system_service"] = system_service
    app.config["update_service"] = update_service
    app.config["data_handler"] = data_handler
    app.config["ssl_enabled"] = ssl_enabled

    # CSRF protection helpers
    def ensure_csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def validate_csrf_token():
        token = session.get("csrf_token")
        if not token:
            return False
        submitted = request.form.get("csrf_token")
        if not submitted:
            submitted = request.headers.get("X-CSRF-Token")
        if not submitted and request.is_json:
            data = request.get_json(silent=True) or {}
            submitted = data.get("csrf_token")
        return secrets.compare_digest(token, submitted or "")

    def is_safe_next(next_url):
        if not next_url:
            return None
        if next_url.startswith("/") and not next_url.startswith("//"):
            return next_url
        return None

    def is_authenticated():
        return bool(session.get("user"))

    # Store helpers in app config
    app.config["validate_csrf"] = validate_csrf_token
    app.config["is_safe_next"] = is_safe_next
    app.config["is_authenticated"] = is_authenticated

    # Ensure default user exists
    default_user = user_store.ensure_default_user()
    if default_user:
        config_store.set_values(
            {
                "initial_admin_username": default_user["username"],
                "initial_admin_password": default_user["password"],
            }
        )

    # Context processor for templates
    @app.context_processor
    def inject_auth_context():
        current_username = session.get("user")
        user_preferences = user_store.get_preferences(current_username)
        return {
            "current_user": current_username,
            "user_preferences": user_preferences,
            "csrf_token": ensure_csrf_token(),
            "force_password_change": session.get("must_change_password", False),
        }

    # Authentication middleware
    @app.before_request
    def check_auth():
        # Public routes that don't require authentication
        public_paths = ["/login", "/static/", "/api/font-file/"]
        current_path = request.path

        # Allow public paths
        for path in public_paths:
            if current_path.startswith(path):
                return None

        # Check authentication
        if not is_authenticated():
            if current_path.startswith("/api/"):
                return jsonify({"error": "authentication_required"}), 401
            next_url = is_safe_next(request.full_path or request.path)
            return redirect(url_for("auth.login", next=next_url))

        # Check if password change is required
        if session.get("must_change_password") and current_path not in [
            "/change-password",
            "/logout",
        ]:
            if current_path.startswith("/api/"):
                return jsonify({"error": "password_change_required"}), 403
            return redirect(url_for("auth.change_password"))

        return None

    # Register blueprints
    from web.blueprints.auth import create_auth_blueprint

    auth_bp = create_auth_blueprint(
        user_store, config_store, validate_csrf_token, is_safe_next
    )
    app.register_blueprint(auth_bp)

    # Helper functions for index route
    def get_commit_version():
        """Get the latest git commit version info."""
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            result = run_command(
                ["git", "log", "-1", "--format=%h - %s (%ad)", "--date=format:%b %d, %Y %I:%M %p"],
                cwd=cwd,
                timeout_s=5,
                log_label="git_latest_commit",
            )
            if result.ok and result.stdout.strip():
                return result.stdout.strip()
            return "Not available"
        except Exception:
            return "Not available"

    def check_for_updates():
        """Check if git updates are available."""
        try:
            configured_branch = config_store.get_str("git_branch", "main")
            local_head, remote_head = update_service.get_heads(timeout=5, branch=configured_branch)
            if not local_head or not remote_head:
                return False
            return local_head != remote_head
        except Exception:
            return False

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            device_ip=system_service.get_device_ip(),
            tailscale_address=system_service.get_tailscale_address(),
            commit_version=get_commit_version(),
            ssl_enabled=ssl_enabled,
            display_name=config_store.get_str("title_text", "Nicole's Train Tracker!"),
            update_available=check_for_updates(),
        )

    return app, ssl_context, ssl_enabled
