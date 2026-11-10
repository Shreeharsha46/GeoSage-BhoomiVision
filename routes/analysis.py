"""
Analysis blueprint (Stage 3): run image comparisons and present results.

Flow: New Analysis form -> POST (uploads or selected stored images) ->
full CV pipeline -> persistence (analysis row, region rows, land-use
observations, artifacts) -> detail page with explainable outputs,
heatmap viewer and verification status.

Every computation happens on the backend through modules/pipeline.py.
Results are labelled visual-change findings, never legal evidence.
"""
import json
from datetime import date
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from config import BASE_DIR
from database.db import db
from database.models import (AnalysisResult, BoundaryRecord, DetectedRegion,
                             LandImage, LandParcel, LandUseObservation,
                             ReviewRecord)
from modules.pipeline import run_analysis
from routes.helpers import get_analysis_or_denied, get_parcel_or_denied, scope_parcels
from routes.uploads import UploadError, generate_stored_name, validate_image

analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")

ARTIFACT_KEYS = ["difference", "mask", "heatmap", "overlay", "registered",
                 "side_by_side"]


def _store_uploaded_image(parcel, file_input, image_type, image_date_raw):
    """Validate + persist one uploaded image for the parcel. Returns id."""
    if file_input is None or not file_input.filename:
        return None
    data = file_input.read()
    validate_image(data, file_input.filename,
                   current_app.config["ALLOWED_IMAGE_EXTENSIONS"])
    ext = file_input.filename.rsplit(".", 1)[-1].lower()
    folder = Path(current_app.config["OLD_IMAGE_FOLDER"])
    if image_type == "recent":
        folder = Path(current_app.config["RECENT_IMAGE_FOLDER"])
    stored = folder / generate_stored_name(ext)
    stored.write_bytes(data)

    image = LandImage(parcel=parcel, image_type=image_type,
                      image_path=stored.relative_to(BASE_DIR).as_posix())
    if image_date_raw:
        try:
            image.image_date = date.fromisoformat(image_date_raw)
        except ValueError:
            flash("Capture date ignored (expected YYYY-MM-DD).", "warning")
    db.session.add(image)
    db.session.flush()          # get the id without committing everything
    return image.id


def _resolve_image(parcel, image_id, upload_file, image_type, date_raw):
    """Prefer an uploaded file; fall back to a selected stored image;
    and finally to the latest image of the matching type already
    attached to the parcel (so the New Analysis form works without
    having to re-upload images every time)."""
    uploaded = _store_uploaded_image(parcel, upload_file, image_type, date_raw)
    if uploaded:
        return uploaded
    if image_id:
        image = db.session.get(LandImage, int(image_id))
        if image is None or image.parcel_id != parcel.id:
            abort(400, description="Selected image does not belong to this parcel.")
        return image.id
    # Fall back to the most recent image of the requested type on this parcel.
    latest = (db.session.query(LandImage)
              .filter_by(parcel_id=parcel.id, image_type=image_type)
              .order_by(LandImage.id.desc()).first())
    if latest is None:
        return None
    return latest.id


def _latest_boundary_iou(parcel):
    """Most recent boundary IoU recorded for this parcel (may be None)."""
    record = (db.session.query(BoundaryRecord)
              .filter(BoundaryRecord.parcel_id == parcel.id,
                      BoundaryRecord.comparison_json.isnot(None))
              .order_by(BoundaryRecord.id.desc()).first())
    if not record:
        return None
    try:
        return json.loads(record.comparison_json).get("iou")
    except (json.JSONDecodeError, AttributeError):
        return None


def _previous_changes(parcel, exclude_id=None):
    """Earlier change percentages for the parcel (history nudge input)."""
    query = (db.session.query(AnalysisResult.change_percentage)
             .filter(AnalysisResult.parcel_id == parcel.id)
             .order_by(AnalysisResult.analysis_date.desc()))
    values = [row[0] for row in query.all() if row[0] is not None]
    return values


@analysis_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_analysis():
    parcels = scope_parcels(db.session.query(LandParcel)).order_by(
        LandParcel.parcel_name).all()

    if request.method == "GET":
        return render_template("analysis/new.html", parcels=parcels)

    parcel_id = request.form.get("parcel_id", type=int)
    if not parcel_id:
        flash("Please select a land parcel.", "danger")
        return render_template("analysis/new.html", parcels=parcels)
    parcel = get_parcel_or_denied(parcel_id)

    old_date = (request.form.get("old_image_date") or "").strip()
    new_date = (request.form.get("new_image_date") or "").strip()

    try:
        db.session.begin_nested()
        old_image_id = _resolve_image(parcel, request.form.get("old_image_id"),
                                      request.files.get("old_image"), "old", old_date)
        new_image_id = _resolve_image(parcel, request.form.get("new_image_id"),
                                      request.files.get("new_image"), "recent", new_date)
        if not old_image_id or not new_image_id:
            db.session.rollback()
            flash("A previous AND a recent image are required - upload them or "
                  "select images already attached to the parcel.", "danger")
            return render_template("analysis/new.html", parcels=parcels,
                                   selected_parcel=parcel.id)
    except UploadError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return render_template("analysis/new.html", parcels=parcels)

    # Optional boundary file uploaded alongside the analysis (Stage 4 hook)
    boundary_file = request.files.get("boundary_file")
    boundary_error = None
    if boundary_file and boundary_file.filename:
        from routes.boundaries import store_boundary_file
        try:
            store_boundary_file(parcel, boundary_file)
            flash("Boundary file attached to the parcel.", "success")
        except (UploadError, ValueError) as exc:
            boundary_error = str(exc)

    analysis = AnalysisResult(parcel=parcel, old_image_id=old_image_id,
                              new_image_id=new_image_id,
                              processing_method="ORB registration + difference change detection")
    db.session.add(analysis)
    db.session.commit()

    # ---- Run the pipeline (synchronous; downscaled images keep this fast) ----
    old_img = db.session.get(LandImage, old_image_id)
    new_img = db.session.get(LandImage, new_image_id)
    result = run_analysis(
        Path(BASE_DIR) / old_img.image_path,
        Path(BASE_DIR) / new_img.image_path,
        Path(current_app.config["HEATMAP_FOLDER"]).parent,  # outputs/
        analysis.id,
        previous_changes=_previous_changes(parcel),
        boundary_iou=_latest_boundary_iou(parcel),
    )

    # ---- Persist --------------------------------------------------------------
    analysis.processing_metadata = json.dumps({
        "registration": result["registration"],
        "quality": result["quality"],
        "processing_seconds": result["processing_seconds"],
    })
    analysis.artifacts = json.dumps(result.get("artifacts", {}))

    if result["status"] == "ok":
        analysis.change_percentage = result["change"]["change_percentage"]
        analysis.review_priority = result["priority"]["label"]
        summary_bits = [
            f"Visual change {result['change']['change_percentage']:.2f}% of the "
            f"valid comparison area ({result['change']['changed_pixels']:,} of "
            f"{result['change']['valid_pixels']:,} px changed).",
            f"{len(result['regions'])} region(s) flagged.",
            f"Review priority: {result['priority']['label']}.",
        ]
        if result["change"].get("note"):
            summary_bits.append(result["change"]["note"])
        analysis.result_summary = " ".join(summary_bits)

        for index, region in enumerate(result["regions"], start=1):
            db.session.add(DetectedRegion(
                analysis=analysis,
                region_type="visual_change",
                pixel_area=region["pixel_area"],
                geographic_area=None,  # set only with a valid scale (never invented)
                confidence=None,       # classical CV carries no calibrated confidence
                priority=region["priority"],
                explanation=region["explanation"]["reason"],
                bbox=json.dumps(region["bbox"]),
                centroid=json.dumps(region["centroid"]),
                mean_intensity=region["mean_intensity"],
                detection_method=region["detection_method"],
            ))

        for observation in result["landuse"]["transitions"]:
            db.session.add(LandUseObservation(
                analysis_id=analysis.id,
                category=observation["category"],
                old_proportion=observation["old"],
                new_proportion=observation["new"],
                delta_proportion=observation["delta"],
            ))
        analysis.result_summary += " " + _landuse_summary(result["landuse"])

        db.session.add(ReviewRecord(analysis=analysis, reviewer=current_user,
                                    review_status=ReviewRecord.STATUS_PENDING,
                                    previous_status=None,
                                    comments="Initial status after analysis."))
        db.session.commit()

        flash("Analysis complete. Results below are visual-change findings, "
              "not confirmed land changes.", "success")
        return redirect(url_for("analysis.analysis_detail", analysis_id=analysis.id))

    if result["status"] == "registration_failed":
        analysis.result_summary = (
            "Registration failed - no change measurement produced. "
            + result["explanation"]["reason"]
        )
        analysis.review_priority = "insufficient_data"
        analysis.change_percentage = None
    else:
        analysis.result_summary = "Comparison failed: " + result.get("reason", "")
        analysis.review_priority = "insufficient_data"
    db.session.commit()

    if boundary_error:
        flash(boundary_error, "warning")
    flash("Analysis recorded with limitations - see the details.", "warning")
    return redirect(url_for("analysis.analysis_detail", analysis_id=analysis.id))


def _landuse_summary(landuse):
    if not landuse["transitions"]:
        return "No notable land-use proportion shifts (baseline observations)."
    top = landuse["transitions"][0]
    return (f"Largest land-use shift (baseline): {top['label']} "
            f"{top['direction']} from {top['old'] * 100:.1f}% to "
            f"{top['new'] * 100:.1f}%.")


@analysis_bp.route("/")
@login_required
def list_analyses():
    parcel_ids = [p.id for p in scope_parcels(db.session.query(LandParcel)).all()]
    analyses = (db.session.query(AnalysisResult)
                .filter(AnalysisResult.parcel_id.in_(parcel_ids) if parcel_ids else db.false())
                .order_by(AnalysisResult.analysis_date.desc()).all())
    return render_template("analysis/list.html", analyses=analyses)


@analysis_bp.route("/<int:analysis_id>")
@login_required
def analysis_detail(analysis_id):
    analysis = get_analysis_or_denied(analysis_id)
    metadata = {}
    try:
        metadata = json.loads(analysis.processing_metadata or "{}")
    except json.JSONDecodeError:
        pass
    regions = analysis.regions
    explanations = []

    landuse = db.session.query(LandUseObservation).filter_by(
        analysis_id=analysis.id).all()
    review = (db.session.query(ReviewRecord)
              .filter_by(analysis_id=analysis.id)
              .order_by(ReviewRecord.reviewed_at.desc()).first())

    parcels = scope_parcels(db.session.query(LandParcel)).all()
    artifacts_json = json.loads(analysis.artifacts or "{}")
    return render_template(
        "analysis/detail.html", analysis=analysis, metadata=metadata,
        regions=regions, landuse=landuse, review=review,
        artifact_keys=ARTIFACT_KEYS, parcels=parcels,
        artifacts_json=artifacts_json,
    )


@analysis_bp.route("/<int:analysis_id>/delete", methods=["POST"])
@login_required
def delete_analysis(analysis_id):
    analysis = get_analysis_or_denied(analysis_id)
    db.session.delete(analysis)
    db.session.commit()
    flash("Analysis and its results were deleted.", "info")
    return redirect(url_for("analysis.list_analyses"))


@analysis_bp.route("/api/<int:analysis_id>/regions")
@login_required
def region_api(analysis_id):
    """Region list for the heatmap viewer / tables (JSON)."""
    analysis = get_analysis_or_denied(analysis_id)
    regions = []
    for index, region in enumerate(analysis.regions, start=1):
        try:
            bbox = json.loads(region.bbox or "null")
            centroid = json.loads(region.centroid or "null")
        except json.JSONDecodeError:
            bbox, centroid = None, None
        regions.append({
            "index": index, "id": region.id, "pixel_area": region.pixel_area,
            "bbox": bbox, "centroid": centroid,
            "mean_intensity": region.mean_intensity,
            "priority": region.priority,
            "explanation": region.explanation,
        })
    return jsonify(analysis_id=analysis.id,
                   change_percentage=analysis.change_percentage,
                   regions=regions)
