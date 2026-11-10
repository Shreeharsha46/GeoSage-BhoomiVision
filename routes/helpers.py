"""
Shared route helpers: ownership checks and permission-scoped queries.

Security rule: analysts may only ever reach their own parcels/images/
analyses/reports; administrators may reach everything. These checks run
on the backend for every protected resource (never only in the UI).
"""
from flask import abort
from flask_login import current_user
from sqlalchemy import inspect as sql_inspect

from database.db import db
from database.models import AnalysisResult, LandParcel, User


def is_admin():
    return current_user.is_authenticated and current_user.role == "admin"


def scope_parcels(query):
    """Return the parcel query limited to what the current user may see."""
    if is_admin():
        return query
    return query.filter_by(user_id=current_user.id)


def get_parcel_or_denied(parcel_id):
    """Fetch a parcel owned by the current user (or any parcel for admins)."""
    parcel = db.session.get(LandParcel, parcel_id)
    if parcel is None:
        abort(404)
    if parcel.user_id != current_user.id and not is_admin():
        abort(403)  # cross-user access attempt
    return parcel


def get_analysis_or_denied(analysis_id):
    """Fetch an analysis whose parcel is owned by the current user."""
    analysis = db.session.get(AnalysisResult, analysis_id)
    if analysis is None:
        abort(404)
    if analysis.parcel.user_id != current_user.id and not is_admin():
        abort(403)
    return analysis


def can_review():
    """Only administrators record verification decisions (Stage 6)."""
    return is_admin()


def all_users():
    """List users (admin-only helper)."""
    if not is_admin():
        abort(403)
    return db.session.query(User).order_by(User.created_at).all()


def db_tables():
    return set(sql_inspect(db.engine).get_table_names())
