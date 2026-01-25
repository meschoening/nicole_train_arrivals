"""Authentication blueprint for login, logout, and user management."""

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify


def create_auth_blueprint(user_store, config_store, validate_csrf_fn, is_safe_next_fn):
    """Create the authentication blueprint.

    Args:
        user_store: UserStore instance for user management
        config_store: ConfigStore instance for configuration
        validate_csrf_fn: Function to validate CSRF tokens
        is_safe_next_fn: Function to validate next URL redirects

    Returns:
        Blueprint: Flask blueprint for auth routes
    """
    bp = Blueprint("auth", __name__)

    @bp.get("/login")
    def login():
        """Render the login page."""
        initial_user = config_store.get_str("initial_admin_username", "")
        initial_pass = config_store.get_str("initial_admin_password", "")
        return render_template(
            "login.html",
            initial_username=initial_user,
            initial_password=initial_pass,
        )

    @bp.post("/login")
    def login_submit():
        """Handle login form submission."""
        if not validate_csrf_fn():
            return render_template("login.html", error="Invalid request"), 400

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        ok, must_change = user_store.check_password(username, password)
        if not ok:
            return render_template("login.html", error="Invalid credentials"), 401

        session["user"] = username
        session["must_change_password"] = must_change

        if must_change:
            return redirect(url_for("auth.change_password"))

        # Clear initial credentials if this user just logged in
        if username == config_store.get_str("initial_admin_username", ""):
            config_store.set_values(
                {"initial_admin_username": "", "initial_admin_password": ""}
            )

        next_url = is_safe_next_fn(request.args.get("next"))
        return redirect(next_url or url_for("settings_page"))

    @bp.get("/logout")
    def logout():
        """Handle logout."""
        session.pop("user", None)
        session.pop("must_change_password", None)
        return redirect(url_for("auth.login"))

    @bp.get("/change-password")
    def change_password():
        """Render the change password page."""
        if not session.get("user"):
            return redirect(url_for("auth.login"))
        return render_template("change_password.html")

    @bp.post("/change-password")
    def change_password_submit():
        """Handle change password form submission."""
        if not session.get("user"):
            return redirect(url_for("auth.login"))

        if not validate_csrf_fn():
            return render_template("change_password.html", error="Invalid request"), 400

        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        username = session.get("user")

        # Verify current password
        ok, _ = user_store.check_password(username, current_password)
        if not ok:
            return render_template(
                "change_password.html", error="Current password is incorrect"
            ), 400

        # Validate new password
        if len(new_password) < 6:
            return render_template(
                "change_password.html",
                error="New password must be at least 6 characters",
            ), 400

        if new_password != confirm_password:
            return render_template(
                "change_password.html", error="New passwords do not match"
            ), 400

        # Update password
        if not user_store.set_password(username, new_password):
            return render_template(
                "change_password.html", error="Failed to update password"
            ), 500

        session["must_change_password"] = False

        # Clear initial credentials if this user just changed password
        if username == config_store.get_str("initial_admin_username", ""):
            config_store.set_values(
                {"initial_admin_username": "", "initial_admin_password": ""}
            )

        return redirect(url_for("settings_page"))

    @bp.get("/users")
    def users():
        """Render the user management page."""
        all_users = user_store.list_users()
        current = session.get("user")
        return render_template("users.html", users=all_users, current_user=current)

    @bp.post("/users/add")
    def add_user():
        """Add a new user."""
        if not validate_csrf_fn():
            return jsonify({"error": "Invalid request"}), 400

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400

        if not user_store.add_user(username, password):
            return jsonify({"error": "Failed to add user"}), 500

        return redirect(url_for("auth.users"))

    @bp.post("/users/password")
    def change_user_password():
        """Change a user's password."""
        if not validate_csrf_fn():
            return jsonify({"error": "Invalid request"}), 400

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            return jsonify({"error": "Username and password required"}), 400

        if not user_store.set_password(username, password):
            return jsonify({"error": "Failed to change password"}), 500

        return redirect(url_for("auth.users"))

    @bp.post("/users/remove")
    def remove_user():
        """Remove a user."""
        if not validate_csrf_fn():
            return jsonify({"error": "Invalid request"}), 400

        username = request.form.get("username", "").strip()
        current = session.get("user")
        if username == current:
            return jsonify({"error": "Cannot remove yourself"}), 400

        if not user_store.remove_user(username):
            return jsonify({"error": "Failed to remove user"}), 500

        return redirect(url_for("auth.users"))

    @bp.post("/api/user/preferences")
    def update_user_preferences():
        """Update user preferences via API."""
        if not validate_csrf_fn():
            return jsonify({"error": "Invalid request"}), 400

        username = session.get("user")
        if not username:
            return jsonify({"error": "Not authenticated"}), 401

        data = request.get_json(silent=True) or {}

        # Handle sidebar collapsed preference
        sidebar_collapsed = data.get("sidebar_collapsed")
        if sidebar_collapsed is not None:
            user_store.set_preference(username, "sidebar_collapsed", sidebar_collapsed)

        return jsonify({"ok": True})

    return bp
