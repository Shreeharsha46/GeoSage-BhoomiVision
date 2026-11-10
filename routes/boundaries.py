"""
Boundary blueprint (Stage 4): upload / draw / detect / compare polygons.

Coordinate-space discipline (enforced everywhere):
  geographic space = EPSG:4326 lon/lat (uploads, map drawings)
  image space      = pixel x/y (image drawings, detected candidates)

Comparisons run only between records in the SAME space; mixing spaces is
rejected with a clear message. Metric areas are computed in a projected
UTM CRS, never from raw degrees.

Detected candidate boundaries are labelled as image features, never as
legal property boundaries. Screening results are review priorities, not
encroachment verdicts.
"""
import json
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from config import BASE_DIR
from database.db import db
from database.models import (AnalysisResult, BoundaryRecord, LandImage,
                             LandParcel, ReviewRecord)
from modules.boundary_detection import annotate_candidates, detect_candidate_boundaries
from modules.boundaries import (BoundaryError, compare_polygons,
                                geojson_from_coords, parse_geojson, parse_kml,
                                polygon_to_geojson, screen_encroachment)
from modules.preprocessing import decode_bytes, load_stored
from modules.priority import compute_priority
from routes.helpers import get_parcel_or_denied, scope_parcels
from routes.uploads import UploadError

boundaries_bp = Blueprint("boundaries", __name__, url_prefix="/boundaries")

ALLOWED_BOUNDARY_EXTENSIONS = {"geojson", "json", "kml"}
MAX_BOUNDARY_BYTES = 8 * 1024 * 1024


def store_boundary_file(parcel, file_input):
    """Validate + persist an uploaded GeoJSON/KML boundary for a parcel.

    Shared with the analysis form (optional boundary upload). Returns the
    new BoundaryRecord id.
    """
    filename = file_input.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_BOUNDARY_EXTENSIONS:
        raise UploadError("Boundary must be a .geojson, .json or .kml file.")
    data = file_input.read()
    if len(data) > MAX_BOUNDARY_BYTES:
        raise UploadError("Boundary file is larger than the 8 MB limit.")

    text = data.decode("utf-8", errors="replace")
    if ext == "kml":
        polygons, crs_name = parse_kml(text)
    else:
        polygons, crs_name = parse_geojson(text)
    if len(polygons) != 1:
        raise BoundaryError("Please provide exactly one polygon.")

    folder = Path(current_app.config["BOUNDARY_FOLDER"])
    # Never trust the raw filename for the path; only the (validated) extension
    # survives. Strip everything but alphanumerics from the stem.
    safe_stem = "".join(ch for ch in filename.rsplit(".", 1)[0].lower()
                        if ch.isalnum())[:40] or "boundary"
    stored = folder / f"parcel_{parcel.id}_{safe_stem}.{ext}"
    stored.write_text(text, encoding="utf-8")

    record = BoundaryRecord(
        parcel=parcel, boundary_file=stored.relative_to(BASE_DIR).as_posix(),
        geometry_type="Polygon", coordinate_reference_system=crs_name,
        source="upload", space="geographic", label=f"Uploaded boundary ({ext.upper()})",
        geometry_json=json.dumps([[float(x), float(y)]
                                  for x, y in polygons[0].exterior.coords]),
    )
    db.session.add(record)
    db.session.flush()
    return record.id


@boundaries_bp.route("/")
@login_required
def index():
    parcels = scope_parcels(db.session.query(LandParcel)).order_by(
        LandParcel.parcel_name).all()
    boundary_map = {}
    for parcel in parcels:
        boundary_map[parcel.id] = (db.session.query(BoundaryRecord)
                                   .filter_by(parcel_id=parcel.id)
                                   .order_by(BoundaryRecord.id.desc()).all())
    return render_template("boundaries/index.html", parcels=parcels,
                           boundary_map=boundary_map)


@boundaries_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    parcel = get_parcel_or_denied(request.form.get("parcel_id", type=int))
    file_input = request.files.get("boundary_file")
    if file_input is None or not file_input.filename:
        flash("Choose a GeoJSON or KML file.", "danger")
        return redirect(url_for("boundaries.index"))
    try:
        record_id = store_boundary_file(parcel, file_input)
        db.session.commit()
        flash("Boundary uploaded and validated (WGS84 geographic coordinates).",
              "success")
        return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))
    except (UploadError, BoundaryError, UnicodeDecodeError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("boundaries.index"))


@boundaries_bp.route("/parcel/<int:parcel_id>")
@login_required
def parcel_view(parcel_id):
    parcel = get_parcel_or_denied(parcel_id)
    records = (db.session.query(BoundaryRecord).filter_by(parcel_id=parcel.id)
               .order_by(BoundaryRecord.id.desc()).all())
    images = (db.session.query(LandImage).filter_by(parcel_id=parcel.id)
              .order_by(LandImage.id.desc()).all())
    # latest comparison, if any
    latest = next((r for r in records if r.comparison_json), None)
    comparison = json.loads(latest.comparison_json) if latest else None
    return render_template("boundaries/parcel.html", parcel=parcel,
                           records=records, images=images, comparison=comparison)


@boundaries_bp.route("/parcel/<int:parcel_id>/draw", methods=["POST"])
@login_required
def draw(parcel_id):
    """Save a polygon drawn in the UI (Leaflet map or image canvas)."""
    parcel = get_parcel_or_denied(parcel_id)
    space = request.form.get("space") or "geographic"
    if space not in ("geographic", "image"):
        abort(400, description="Unknown polygon space.")
    label = (request.form.get("label") or "").strip() or (
        "Drawn on map" if space == "geographic" else "Drawn on image")
    try:
        coords = json.loads(request.form.get("coordinates") or "[]")
        poly = geojson_from_coords(coords, space=space)
    except (json.JSONDecodeError, BoundaryError, ValueError, TypeError) as exc:
        flash(f"Invalid polygon: {exc}", "danger")
        return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))

    record = BoundaryRecord(
        parcel=parcel, geometry_type="Polygon",
        coordinate_reference_system="EPSG:4326" if space == "geographic" else None,
        source="manual", space=space, label=label,
        geometry_json=json.dumps([[float(x), float(y)]
                                  for x, y in poly.exterior.coords]),
    )
    db.session.add(record)
    db.session.commit()
    flash("Drawn polygon saved.", "success")
    return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))


@boundaries_bp.route("/parcel/<int:parcel_id>/detect", methods=["POST"])
@login_required
def detect(parcel_id):
    """Candidate boundary detection on a stored image (image space)."""
    parcel = get_parcel_or_denied(parcel_id)
    image = db.session.get(LandImage, request.form.get("image_id", type=int))
    if image is None or image.parcel_id != parcel.id:
        flash("Select an image belonging to this parcel.", "danger")
        return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))

    from modules.preprocessing import load_stored
    bgr = load_stored(str(Path(BASE_DIR) / image.image_path))
    candidates = detect_candidate_boundaries(bgr)
    if not candidates:
        flash("No candidate boundary features were detected in that image.",
              "warning")
        return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))

    for index, poly in enumerate(candidates, start=1):
        db.session.add(BoundaryRecord(
            parcel=parcel, geometry_type="Polygon", source="detected",
            space="image", label=f"Candidate {index} (image features, {int(poly['area_px']):,} px)",
            geometry_json=json.dumps(poly["points"]),
        ))
    db.session.commit()
    flash(f"{len(candidates)} candidate boundary feature(s) saved. These are "
          "IMAGE features, not legal property boundaries.", "warning")
    return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))


@boundaries_bp.route("/record/<int:record_id>/delete", methods=["POST"])
@login_required
def delete_record(record_id):
    record = db.session.get(BoundaryRecord, record_id)
    if record is None:
        abort(404)
    parcel = get_parcel_or_denied(record.parcel_id)
    db.session.delete(record)
    db.session.commit()
    flash("Boundary record deleted.", "info")
    return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))


@boundaries_bp.route("/record/<int:record_id>/geojson")
@login_required
def record_geojson(record_id):
    """Ring coordinates as GeoJSON for map/canvas overlays."""
    record = db.session.get(BoundaryRecord, record_id)
    if record is None:
        abort(404)
    get_parcel_or_denied(record.parcel_id)
    try:
        coords = json.loads(record.geometry_json or "[]")
    except json.JSONDecodeError:
        abort(404)
    ring = coords + [coords[0]] if coords else []
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"label": record.label, "space": record.space,
                       "source": record.source},
    }


@boundaries_bp.route("/parcel/<int:parcel_id>/compare", methods=["POST"])
@login_required
def compare(parcel_id):
    """Compare a recorded boundary with a candidate/drawn polygon."""
    parcel = get_parcel_or_denied(parcel_id)
    recorded_id = request.form.get("recorded_id", type=int)
    candidate_id = request.form.get("candidate_id", type=int)
    recorded = db.session.get(BoundaryRecord, recorded_id)
    candidate = db.session.get(BoundaryRecord, candidate_id)
    if (recorded is None or candidate is None
            or recorded.parcel_id != parcel.id or candidate.parcel_id != parcel.id):
        flash("Both polygons must belong to this parcel.", "danger")
        return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))

    if recorded.space != candidate.space:
        flash("Incompatible coordinate spaces: a geographic boundary cannot be "
              "compared with an image-space polygon. Compare like with like.",
              "danger")
        return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))

    try:
        poly_a = geojson_from_coords(json.loads(recorded.geometry_json or "[]"),
                                     space=recorded.space)
        poly_b = geojson_from_coords(json.loads(candidate.geometry_json or "[]"),
                                     space=candidate.space)
    except (json.JSONDecodeError, BoundaryError, ValueError, TypeError) as exc:
        flash(f"Could not compare polygons: {exc}", "danger")
        return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))

    metrics = compare_polygons(poly_a, poly_b, space=recorded.space)
    screening = screen_encroachment(poly_a, poly_b)
    result = {**metrics, **screening}

    candidate.comparison_json = json.dumps(result)
    db.session.commit()

    # Feed the result back into the parcel's latest analysis so reports,
    # priority and the assistant reflect the boundary screening.
    latest_analysis = (db.session.query(AnalysisResult)
                       .filter_by(parcel_id=parcel.id)
                       .order_by(AnalysisResult.analysis_date.desc()).first())
    if latest_analysis and latest_analysis.change_percentage is not None:
        metadata = json.loads(latest_analysis.processing_metadata or "{}")
        registration = metadata.get("registration", {})
        quality = metadata.get("quality", {})
        label, breakdown = compute_priority(
            change_percentage=latest_analysis.change_percentage,
            boundary_iou=result.get("iou"),
            image_quality={"quality_a": quality.get("old"),
                           "quality_b": quality.get("new")},
            registration={"inlier_ratio": registration.get("inlier_ratio"),
                          "median_reprojection_error":
                              registration.get("median_reprojection_error")},
        )
        latest_analysis.boundary_summary = json.dumps({
            "recorded_id": recorded.id, "candidate_id": candidate.id,
            "iou": result.get("iou"), "priority": screening["priority"],
            "outside_share": screening["outside_share"],
            "missing_share": screening["missing_share"],
            "displacement": screening["displacement"],
            "unit": result.get("unit"),
            "note": screening["note"],
            "priority_breakdown": breakdown,
        })
        latest_analysis.review_priority = label
        db.session.commit()

    flash(f"Comparison complete - screening priority: {screening['priority']}. "
          "This is a review priority, not a legal conclusion.", "info")
    return redirect(url_for("boundaries.parcel_view", parcel_id=parcel.id))
