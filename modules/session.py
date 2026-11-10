"""
User session management module.

Core authentication flow with role-based access control.
Users can register, login, logout. Passwords are hashed with Werkzeug.
Admin users have elevated privileges. All user state is stored in SQLite.
"""
from typing import Any

from flask import request
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from database.db import db
from database.models import User as UserModel
from config import config_by_name
from app import create_app
import os

class SessionManager:
    """Manage user sessions in the Flask application."""

    def __init__(self, app=None):
        self.app = app or create_app()
        self.app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

    def register_user(self, user_data: Dict[str, Any]) -> UserModel:
        """Register a new user and save to the database."""
        # Validate input
        name = user_data.get("name", "").strip()
        email = user_data.get("email", "").strip().lower()
        password = user_data.get("password", "")
        confirm = user_data.get("confirm", "")

        # Basic validation
        if not name or len(name) < 2:
            raise ValueError("Please enter a valid name (min. 2 characters).")
        if not email or "@" not in email:
            raise ValueError("Please enter a valid email address.")
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if password != confirm:
            raise ValueError("Passwords do not match.")

        # Check if user already exists
        if UserModel.query.filter_by(email=email).first():
            raise ValueError("An account with this email already exists.")

        # Create user
        user = UserModel(name=name, email=email, role="analyst")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    def login_user(self, email: str, password: str) -> bool:
        """Authenticate user and return success status."""
        user = UserModel.query.filter_by(email=email).first()
        if not user:
            return False

        if not user.check_password(password):
            return False

        if not user.is_active:
            raise ValueError("This account has been deactivated by an administrator.")

        # In a real Flask app, you would use Flask-Login here
        # login_user(user)
        return True

    def logout_user(self):
        """Log out the current user."""
        # In a real Flask app, you would use Flask-Logout here
        pass

    def get_current_user(self) -> UserModel:
        """Get the currently logged-in user."""
        # In a real Flask app, you would use current_user here
        return None

    def is_admin(self, user: UserModel) -> bool:
        """Check if user has admin privileges."""
        return user and user.role == "admin"
