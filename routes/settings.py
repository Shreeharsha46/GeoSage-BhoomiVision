"""
Settings blueprint: profile management, password change and a system
information panel (real library versions, useful in the viva demo).
"""
import sys

import cv2
import flask
import numpy
import sqlalchemy
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required

from database.db import db
from routes.auth import password_problem

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/")
@login_required
def index():
    system_info = {
        "Python": sys.version.split()[0],
        "Flask": flask.__version__,
        "SQLAlchemy": sqlalchemy.__version__,
        "OpenCV": cv2.__version__,
        "NumPy": numpy.__version__,
    }
    return render_template("settings.html", system_info=system_info)


@settings_bp.route("/profile", methods=["POST"])
@login_required
def update_profile():
    name = (request.form.get("name") or "").strip()
    if len(name) < 2:
        flash("Please enter a valid name.", "danger")
    else:
        current_user.name = name
        db.session.commit()
        flash("Profile updated.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    if not current_user.check_password(current):
        flash("Current password is incorrect.", "danger")
    elif new != confirm:
        flash("New passwords do not match.", "danger")
    else:
        problem = password_problem(new)
        if problem:
            flash(problem, "danger")
        else:
            current_user.set_password(new)
            db.session.commit()
            flash("Password changed successfully.", "success")
    return redirect(url_for("settings.index"))
