"""
Land-use monitoring blueprint (Stage 5).

Displays the classical land-use baseline observations stored with each
analysis: category proportions, transitions between the two captures and
segmentation overview images. Everything on the page is labelled as a
heuristic baseline observation - NOT a trained-model prediction.
"""
import json

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from database.db import db
from database.models import AnalysisResult, LandUseObservation
from modules.landuse import CATEGORY_LABELS, CATEGORIES
from routes.helpers import get_analysis_or_denied, scope_parcels

landuse_bp = Blueprint("landuse", __name__, url_prefix="/landuse")


def _analyses_for_current_user():
    """Analyses the current user may see, newest first."""
    from database.models import LandParcel
    ids = [p.id for p in scope_parcels(db.session.query(LandParcel)).all()]
    query = db.session.query(AnalysisResult).order_by(AnalysisResult.analysis_date.desc())
    return query.filter(AnalysisResult.parcel_id.in_(ids)) if ids else query.filter(db.false())


@landuse_bp.route("/")
@login_required
def index():
    analyses = _analyses_for_current_user().limit(60).all()
    selected_id = request.args.get("analysis", type=int)
    selected = None
    observations = []
    if selected_id:
        analysis = get_analysis_or_denied(selected_id)
        selected = analysis
        observations = (db.session.query(LandUseObservation)
                        .filter_by(analysis_id=analysis.id)
                        .order_by(LandUseObservation.delta_proportion.desc()).all())
    return render_template("landuse/index.html", analyses=analyses,
                           selected=selected, observations=observations,
                           labels=CATEGORY_LABELS, categories=CATEGORIES)
