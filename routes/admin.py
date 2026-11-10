"""
Administrator blueprint: manage authorized users.

Admin-only routes (enforced server side): list users with activity,
deactivate/reactivate accounts, and switch roles between analyst and
admin. Deactivated users cannot log in (Flask-Login honours is_active).
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from database.db import db
from routes.helpers import all_users, is_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/users")
@login_required
def users():
    if not is_admin():
        flash("Administrator access required.", "danger")
        return redirect(url_for("main.dashboard"))
    people = all_users()
    # attach activity counts (real queries, no guesswork)
    from database.models import AnalysisResult, LandParcel
    for person in people:
        person.parcel_count = (
            db.session.query(LandParcel).filter_by(user_id=person.id).count()
        )
        person.analysis_count = (
            db.session.query(AnalysisResult)
            .join(LandParcel, AnalysisResult.parcel_id == LandParcel.id)
            .filter(LandParcel.user_id == person.id)
            .count()
        )
    return render_template("admin/users.html", people=people)


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_user(user_id):
    if not is_admin():
        flash("Administrator access required.", "danger")
        return redirect(url_for("main.dashboard"))
    from database.models import User
    person = db.session.get(User, user_id)
    if person is None:
        flash("User not found.", "danger")
    elif person.id == current_user.id:
        flash("You cannot deactivate your own account.", "warning")
    else:
        person.is_active = not person.is_active
        db.session.commit()
        state = "activated" if person.is_active else "deactivated"
        flash(f"Account {person.email} {state}.", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
@login_required
def change_role(user_id):
    if not is_admin():
        flash("Administrator access required.", "danger")
        return redirect(url_for("main.dashboard"))
    from database.models import User
    person = db.session.get(User, user_id)
    role = request.form.get("role")
    if person is None or role not in ("admin", "analyst"):
        flash("Invalid user or role.", "danger")
    elif person.id == current_user.id:
        flash("You cannot change your own role.", "warning")
    else:
        person.role = role
        db.session.commit()
        flash(f"{person.email} is now a {role}.", "info")
    return redirect(url_for("admin.users"))
