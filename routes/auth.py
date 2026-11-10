"""
Authentication blueprint: registration, login, logout.

- Passwords are hashed with Werkzeug (never stored in plain text).
- Password strength is validated server-side.
- Duplicate e-mails are rejected with a clear message.
- Public registration always creates the 'analyst' role; the 'admin'
  role is created by the seed routine on first startup.
"""
import re

from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from database.db import db
from database.models import User

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def password_problem(password):
    """Return an error message for weak passwords, or None when strong enough.

    Policy: at least 8 characters, at least one letter and one digit.
    """
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password):
        return "Password must contain at least one letter."
    if not re.search(r"\d", password):
        return "Password must contain at least one digit."
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        user = db.session.query(User).filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash("Invalid e-mail or password.", "danger")
        elif not user.is_active:
            flash("This account has been deactivated by an administrator.", "warning")
        else:
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.name}!", "success")
            next_page = request.args.get("next")
            # Open-redirect protection: only follow relative next URLs.
            if next_page and next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)
            return redirect(url_for("main.dashboard"))
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = request.form
    if request.method == "POST":
        name = (form.get("name") or "").strip()
        email = (form.get("email") or "").strip().lower()
        password = form.get("password") or ""
        confirm = form.get("confirm") or ""

        errors = []
        if len(name) < 2:
            errors.append("Please enter your full name.")
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid e-mail address.")
        problem = password_problem(password)
        if problem:
            errors.append(problem)
        if password != confirm:
            errors.append("Passwords do not match.")
        if db.session.query(User).filter_by(email=email).first():
            errors.append("An account with this e-mail already exists.")

        if errors:
            for message in errors:
                flash(message, "danger")
        else:
            user = User(name=name, email=email, role="analyst")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Registration successful. Welcome to GeoSage!", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))
