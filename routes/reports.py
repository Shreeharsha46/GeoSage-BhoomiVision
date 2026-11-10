"""
Reports blueprint (Stage 7.1): generate and download ReportLab PDF reports.

Every PDF is built on demand from stored analysis records. Missing data or
images are handled gracefully; the mandatory verification disclaimer and
platform branding (BHOOMI VISION) are included on every report.
"""
from flask import Blueprint, abort, make_response, render_template, request, url_for
from flask_login import current_user, login_required

from database.db import db
from database.models import AnalysisResult, LandParcel
from modules.report import generate_report
from routes.helpers import get_analysis_or_denied, scope_parcels

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
@login_required
def index():
    parcel_ids = [p.id for p in scope_parcels(db.session.query(LandParcel)).all()]
    analyses = (db.session.query(AnalysisResult)
                .filter(AnalysisResult.parcel_id.in_(parcel_ids) if parcel_ids else db.false())
                .order_by(AnalysisResult.analysis_date.desc()).all())
    return render_template("reports/index.html", analyses=analyses)


@reports_bp.route("/<int:analysis_id>/download")
@login_required
def download(analysis_id):
    analysis = get_analysis_or_denied(analysis_id)
    pdf_bytes = generate_report(analysis)
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=geosage_report_analysis_{analysis.id}.pdf"
    )
    return response
