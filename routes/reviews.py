"""
Review blueprint (Stage 6.4): human verification workflow.

Only administrators record verification decisions (backend-enforced).
Every decision appends a ReviewRecord audit row with the reviewer
identity, previous status, new status, comments and timestamp - the
history is never edited, only extended.

A verification decision records a human opinion about the FINDING. It
does not certify a legal boundary and the UI says so.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database.db import db
from database.models import AnalysisResult, ReviewRecord
from routes.helpers import can_review, get_analysis_or_denied, scope_parcels

reviews_bp = Blueprint("reviews", __name__, url_prefix="/reviews")

VALID_TRANSITIONS = {
    ReviewRecord.STATUS_PENDING: {
        ReviewRecord.STATUS_VERIFIED,
        ReviewRecord.STATUS_REJECTED,
    },
    ReviewRecord.STATUS_VERIFIED: {ReviewRecord.STATUS_PENDING,
                                   ReviewRecord.STATUS_REJECTED},
    ReviewRecord.STATUS_REJECTED: {ReviewRecord.STATUS_PENDING,
                                   ReviewRecord.STATUS_VERIFIED},
}

STATUS_LABELS = {
    ReviewRecord.STATUS_PENDING: "Pending Verification",
    ReviewRecord.STATUS_VERIFIED: "Verified by Reviewer",
    ReviewRecord.STATUS_REJECTED: "Rejected as False Detection",
}


def _latest_status(analysis_id):
    record = (db.session.query(ReviewRecord)
              .filter_by(analysis_id=analysis_id)
              .order_by(ReviewRecord.reviewed_at.desc(), ReviewRecord.id.desc())
              .first())
    return record.review_status if record else None


@reviews_bp.route("/")
@login_required
def index():
    """Verification queue: analyses visible to the current user."""
    from database.models import LandParcel
    ids = [p.id for p in scope_parcels(db.session.query(LandParcel)).all()]
    analyses = (db.session.query(AnalysisResult)
                .filter(AnalysisResult.parcel_id.in_(ids) if ids else db.false())
                .order_by(AnalysisResult.analysis_date.desc()).all())
    queue = [{"analysis": a, "status": _latest_status(a.id),
              "can_review": can_review()} for a in analyses]
    return render_template("reviews/index.html", queue=queue,
                           status_labels=STATUS_LABELS)


@reviews_bp.route("/<int:analysis_id>/record", methods=["POST"])
@login_required
def record_decision(analysis_id):
    analysis = get_analysis_or_denied(analysis_id)
    if not can_review():
        flash("Only administrators can record verification decisions.", "danger")
        return redirect(url_for("reviews.index"))

    new_status = request.form.get("status")
    comments = (request.form.get("comments") or "").strip()
    if new_status not in STATUS_LABELS:
        flash("Invalid verification status.", "danger")
        return redirect(url_for("analysis.analysis_detail", analysis_id=analysis_id))

    previous = _latest_status(analysis_id) or ReviewRecord.STATUS_PENDING
    if new_status != previous and new_status not in VALID_TRANSITIONS.get(previous, set()):
        flash(f"Transition '{previous}' -> '{new_status}' is not allowed.",
              "danger")
        return redirect(url_for("analysis.analysis_detail", analysis_id=analysis_id))

    db.session.add(ReviewRecord(
        analysis=analysis, reviewer=current_user, review_status=new_status,
        previous_status=previous, comments=comments or None,
    ))
    db.session.commit()
    flash(f"Verification recorded: {STATUS_LABELS[new_status]}. Note: a "
          "verification decision does not certify a legal boundary.", "info")
    return redirect(url_for("analysis.analysis_detail", analysis_id=analysis_id))


@reviews_bp.route("/<int:analysis_id>/audit")
@login_required
def audit(analysis_id):
    analysis = get_analysis_or_denied(analysis_id)
    records = (db.session.query(ReviewRecord)
               .filter_by(analysis_id=analysis.id)
               .order_by(ReviewRecord.reviewed_at.asc()).all())
    return render_template("reviews/audit.html", analysis=analysis,
                           records=records, status_labels=STATUS_LABELS)
