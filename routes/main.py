"""
Main blueprint: public landing page and the authenticated dashboard.

Dashboard numbers are computed from real database records (scoped to the
current user; administrators see system-wide figures). Nothing here is
hard-coded or invented.
"""
import json

from flask import Blueprint, jsonify, render_template
from flask_login import current_user, login_required

from database.db import db
from database.models import AnalysisResult, DetectedRegion, LandParcel, ReviewRecord
from routes.helpers import is_admin, scope_parcels

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Public landing page (GeoSage / BHOOMI VISION branding)."""
    return render_template("index.html")


@main_bp.route("/health")
def health():
    """Readiness probe used by tests and by the demo checklist."""
    return jsonify(status="ok", app="GeoSage", stage=2)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    parcels_q = scope_parcels(db.session.query(LandParcel)).order_by(LandParcel.created_at)
    parcels = parcels_q.all()
    parcel_ids = [p.id for p in parcels]

    analyses_q = db.session.query(AnalysisResult)
    if parcel_ids:
        analyses_q = analyses_q.filter(AnalysisResult.parcel_id.in_(parcel_ids))
    else:
        analyses_q = analyses_q.filter(db.false())
    analyses = analyses_q.order_by(AnalysisResult.analysis_date.desc()).all()
    analysis_ids = [a.id for a in analyses]

    regions_q = db.session.query(DetectedRegion)
    if analysis_ids:
        regions_q = regions_q.filter(DetectedRegion.analysis_id.in_(analysis_ids))
    else:
        regions_q = regions_q.filter(db.false())
    regions = regions_q.all()

    pending = 0
    if analysis_ids:
        pending = (
            db.session.query(ReviewRecord)
            .filter(ReviewRecord.analysis_id.in_(analysis_ids),
                    ReviewRecord.review_status == ReviewRecord.STATUS_PENDING)
            .count()
        )

    # --- chart data (computed from stored records) ---------------------------
    trend = [
        {
            "date": a.analysis_date.strftime("%Y-%m-%d %H:%M"),
            "change": round(a.change_percentage or 0.0, 2),
            "parcel": a.parcel.parcel_name,
        }
        for a in reversed(list(analyses)[:20])  # chronological order
    ]
    priority_counts = {"low": 0, "medium": 0, "high": 0}
    for r in regions:
        if r.priority in priority_counts:
            priority_counts[r.priority] += 1

    parcel_activity = [
        {
            "id": p.id,
            "name": p.parcel_name,
            "images": len(p.images),
            "analyses": len(p.analyses),
            "georeferenced": p.is_georeferenced,
            "lat": p.latitude,
            "lon": p.longitude,
            "last_change": (
                round(p.analyses[-1].change_percentage, 2)
                if p.analyses and p.analyses[-1].change_percentage is not None else None
            ),
        }
        for p in parcels
    ]

    stats = {
        "total_parcels": len(parcels),
        "total_analyses": len(analyses),
        "changes_detected": len(regions),
        "pending_verification": pending,
    }
    return render_template(
        "dashboard.html", stats=stats, recent=analyses[:8],
        trend=trend, priorities=priority_counts, activity=parcel_activity,
    )


@main_bp.route("/api/dashboard/charts")
@login_required
def dashboard_charts():
    """Chart data for the dashboard, computed from stored analyses."""
    parcel_ids = [p.id for p in scope_parcels(db.session.query(LandParcel)).all()]
    analyses_q = db.session.query(AnalysisResult).order_by(AnalysisResult.analysis_date)
    analyses = (analyses_q.filter(AnalysisResult.parcel_id.in_(parcel_ids)).all()
                if parcel_ids else [])
    analysis_ids = [a.id for a in analyses]

    regions = (db.session.query(DetectedRegion)
               .filter(DetectedRegion.analysis_id.in_(analysis_ids)).all()
               if analysis_ids else [])
    priorities = {"low": 0, "medium": 0, "high": 0, "total": len(regions)}
    for r in regions:
        if r.priority in priorities:
            priorities[r.priority] += 1

    trend = [{"date": a.analysis_date.strftime("%Y-%m-%d %H:%M"),
              "change": round(a.change_percentage or 0.0, 2),
              "parcel": a.parcel.parcel_name} for a in analyses[-20:]]
    return jsonify(trend=trend, priorities=priorities)


@main_bp.route("/api/map/parcels")
@login_required
def map_parcels():
    """GeoJSON of georeferenced parcels for the Leaflet dashboard panel.

    Parcels without coordinates are deliberately EXCLUDED from the map
    (never placed at invented positions) and listed as 'not georeferenced'
    in the UI instead.
    """
    features = []
    unlocated = []
    for p in scope_parcels(db.session.query(LandParcel)).all():
        if not p.is_georeferenced:
            unlocated.append({"id": p.id, "name": p.parcel_name})
            continue
        latest = max(p.analyses, key=lambda a: a.analysis_date, default=None)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [p.longitude, p.latitude]},
            "properties": {
                "id": p.id,
                "name": p.parcel_name,
                "location": p.location or "",
                "crs": p.coordinate_reference_system or "",
                "latest_change": (round(latest.change_percentage, 2)
                                  if latest and latest.change_percentage is not None else None),
                "latest_priority": latest.review_priority if latest else None,
                "analysis_count": len(p.analyses),
            },
        })
    return jsonify({"type": "FeatureCollection", "features": features,
                    "not_georeferenced": unlocated})
