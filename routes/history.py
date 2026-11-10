"""
History blueprint (Stage 6): smart change timeline + analytics.

One parcel can accumulate many images and analyses over time. The
timeline page lists them in order; any two analyses of the same parcel
can be compared side by side. All numbers come from stored records.
"""
import json

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database.db import db
from database.models import (AnalysisResult, BoundaryRecord, LandImage,
                             LandParcel, LandUseObservation, ReviewRecord)
from routes.helpers import get_analysis_or_denied, get_parcel_or_denied, scope_parcels

history_bp = Blueprint("history", __name__, url_prefix="/history")


@history_bp.route("/")
@login_required
def index():
    parcels = scope_parcels(db.session.query(LandParcel)).order_by(
        LandParcel.parcel_name).all()
    selected = None
    timeline = []
    if parcels:
        parcel_id = request.args.get("parcel", type=int)
        selected = next((p for p in parcels if p.id == parcel_id), parcels[0])
        analyses = (db.session.query(AnalysisResult)
                    .filter_by(parcel_id=selected.id)
                    .order_by(AnalysisResult.analysis_date.asc()).all())
        for analysis in analyses:
            latest_review = (db.session.query(ReviewRecord)
                             .filter_by(analysis_id=analysis.id)
                             .order_by(ReviewRecord.reviewed_at.desc()).first())
            landuse_top = (db.session.query(LandUseObservation)
                           .filter_by(analysis_id=analysis.id)
                           .order_by(db.func.abs(LandUseObservation.delta_proportion).desc())
                           .first())
            boundary_summary = None
            try:
                boundary_summary = json.loads(analysis.boundary_summary or "null")
            except json.JSONDecodeError:
                pass
            timeline.append({
                "analysis": analysis,
                "old_date": analysis.old_image.image_date,
                "new_date": analysis.new_image.image_date,
                "review_status": latest_review.review_status if latest_review else None,
                "landuse_top": landuse_top,
                "boundary": boundary_summary,
            })
    return render_template("history/index.html", parcels=parcels,
                           selected=selected, timeline=timeline)


@history_bp.route("/compare")
@login_required
def compare():
    """Compare two analyses of the same parcel side by side."""
    a_id = request.args.get("a", type=int)
    b_id = request.args.get("b", type=int)
    if not a_id or not b_id:
        flash("Pick two analyses to compare.", "warning")
        return redirect(url_for("history.index"))
    analysis_a = get_analysis_or_denied(a_id)
    analysis_b = get_analysis_or_denied(b_id)
    if analysis_a.parcel_id != analysis_b.parcel_id:
        flash("Both analyses must belong to the same parcel.", "danger")
        return redirect(url_for("history.index"))
    if analysis_a.analysis_date > analysis_b.analysis_date:
        analysis_a, analysis_b = analysis_b, analysis_a

    lu_a = (db.session.query(LandUseObservation)
            .filter_by(analysis_id=analysis_a.id).all())
    lu_b = (db.session.query(LandUseObservation)
            .filter_by(analysis_id=analysis_b.id).all())
    lu_by_cat = {o.category: o for o in lu_b}
    lu_rows = [{
        "category": o.category,
        "old": o.old_proportion,
        "a_new": o.new_proportion,
        "b_new": lu_by_cat[o.category].new_proportion if o.category in lu_by_cat else None,
    } for o in lu_a]

    return render_template("history/compare.html", a=analysis_a, b=analysis_b,
                           lu_rows=lu_rows)
