"""
Land parcel management: create / view / edit / delete / search, image
history, and permission-checked media serving.

Media files are stored under uploads/ which is NOT a static folder.
Every /media/... request re-checks ownership in the database before the
file is sent, so one user can never read another user's imagery by
guessing URLs.
"""
import json
from datetime import date
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, send_file, url_for)
from flask_login import current_user, login_required
from sqlalchemy import or_

from config import BASE_DIR
from database.db import db
from database.models import BoundaryRecord, LandImage, LandParcel
from routes.helpers import get_parcel_or_denied, scope_parcels
from routes.uploads import UploadError, generate_stored_name, validate_image

parcels_bp = Blueprint("parcels", __name__, url_prefix="/parcels")
media_bp = Blueprint("media", __name__)

IMAGE_TYPE_LABELS = {"old": "Previous", "recent": "Recent", "extra": "Additional"}


def _parse_coordinates(form):
    """Parse optional lat/lon. Missing values are fine; invalid ones are not."""
    lat_raw = (form.get("latitude") or "").strip()
    lon_raw = (form.get("longitude") or "").strip()
    if not lat_raw and not lon_raw:
        return None, None
    if not lat_raw or not lon_raw:
        raise ValueError("Please provide both latitude and longitude (or leave both empty).")
    try:
        lat, lon = float(lat_raw), float(lon_raw)
    except ValueError:
        raise ValueError("Latitude and longitude must be decimal numbers.")
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise ValueError("Coordinates out of range (lat -90..90, lon -180..180).")
    return lat, lon


def _parcel_from_form(parcel=None):
    """Build/update a LandParcel from submitted form data."""
    name = (request.form.get("parcel_name") or "").strip()
    if len(name) < 2:
        raise ValueError("Please give the parcel a name (min. 2 characters).")
    lat, lon = _parse_coordinates(request.form)
    crs = (request.form.get("coordinate_reference_system") or "").strip() or None

    if parcel is None:
        parcel = LandParcel(
            owner=current_user, parcel_name=name, location=request.form.get("location"),
            latitude=lat, longitude=lon, coordinate_reference_system=crs,
        )
    else:
        parcel.parcel_name = name
        parcel.location = request.form.get("location")
        parcel.latitude = lat
        parcel.longitude = lon
        parcel.coordinate_reference_system = crs
    return parcel


@parcels_bp.route("/")
@login_required
def list_parcels():
    q = (request.args.get("q") or "").strip()
    query = scope_parcels(db.session.query(LandParcel))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(LandParcel.parcel_name.ilike(like),
                                 LandParcel.location.ilike(like)))
    parcels = query.order_by(LandParcel.created_at.desc()).all()
    return render_template("parcels/list.html", parcels=parcels, q=q)


@parcels_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_parcel():
    if request.method == "POST":
        try:
            parcel = _parcel_from_form()
            db.session.add(parcel)
            db.session.commit()
            flash(f"Parcel '{parcel.parcel_name}' created.", "success")
            return redirect(url_for("parcels.parcel_detail", parcel_id=parcel.id))
        except ValueError as exc:
            flash(str(exc), "danger")
    return render_template("parcels/form.html", parcel=None)


@parcels_bp.route("/<int:parcel_id>")
@login_required
def parcel_detail(parcel_id):
    parcel = get_parcel_or_denied(parcel_id)
    images = sorted(parcel.images, key=lambda i: (i.image_date or date.max, i.id))
    return render_template("parcels/detail.html", parcel=parcel, images=images)


@parcels_bp.route("/<int:parcel_id>/edit", methods=["GET", "POST"])
@login_required
def edit_parcel(parcel_id):
    parcel = get_parcel_or_denied(parcel_id)
    if request.method == "POST":
        try:
            _parcel_from_form(parcel)
            db.session.commit()
            flash("Parcel updated.", "success")
            return redirect(url_for("parcels.parcel_detail", parcel_id=parcel.id))
        except ValueError as exc:
            flash(str(exc), "danger")
    return render_template("parcels/form.html", parcel=parcel)


@parcels_bp.route("/<int:parcel_id>/delete", methods=["POST"])
@login_required
def delete_parcel(parcel_id):
    parcel = get_parcel_or_denied(parcel_id)
    name = parcel.parcel_name
    db.session.delete(parcel)  # cascades to images, analyses, regions, reviews
    db.session.commit()
    flash(f"Parcel '{name}' and all its records were deleted.", "info")
    return redirect(url_for("parcels.list_parcels"))


@parcels_bp.route("/<int:parcel_id>/images", methods=["POST"])
@login_required
def add_image(parcel_id):
    """Attach an additional image to a parcel (historical monitoring)."""
    parcel = get_parcel_or_denied(parcel_id)
    file = request.files.get("image")
    image_type = request.form.get("image_type") or "extra"
    if image_type not in IMAGE_TYPE_LABELS:
        image_type = "extra"
    if file is None or file.filename == "":
        flash("Please choose an image file.", "danger")
        return redirect(url_for("parcels.parcel_detail", parcel_id=parcel.id))
    try:
        data = file.read()
        validate_image(data, file.filename,
                       current_app.config["ALLOWED_IMAGE_EXTENSIONS"])
        ext = file.filename.rsplit(".", 1)[-1].lower()
        folder = Path(current_app.config["UPLOAD_FOLDER"]) / "old_images"
        if image_type == "recent":
            folder = Path(current_app.config["RECENT_IMAGE_FOLDER"])
        rel_path = folder / generate_stored_name(ext)
        rel_path.write_bytes(data)
        image = LandImage(
            parcel=parcel, image_type=image_type,
            image_path=rel_path.relative_to(BASE_DIR).as_posix(),
        )
        date_raw = (request.form.get("image_date") or "").strip()
        if date_raw:
            try:
                image.image_date = date.fromisoformat(date_raw)
            except ValueError:
                flash("Capture date ignored (expected YYYY-MM-DD).", "warning")
        db.session.add(image)
        db.session.commit()
        flash("Image added to parcel history.", "success")
    except UploadError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("parcels.parcel_detail", parcel_id=parcel.id))


# ---------------------------------------------------------------------------
# Permission-checked media serving
# ---------------------------------------------------------------------------

def _send_project_file(rel_path, expected_parent):
    """Send a file stored under the project, blocking path traversal."""
    full = (BASE_DIR / rel_path).resolve()
    if not full.is_relative_to(expected_parent.resolve()):
        abort(403)
    if not full.is_file():
        abort(404)
    return send_file(full)


@media_bp.route("/media/image/<int:image_id>")
@login_required
def serve_image(image_id):
    image = db.session.get(LandImage, image_id)
    if image is None:
        abort(404)
    if image.parcel.user_id != current_user.id and current_user.role != "admin":
        abort(403)
    return _send_project_file(image.image_path, current_app.config["UPLOAD_FOLDER"])


@media_bp.route("/media/boundary/<int:boundary_id>")
@login_required
def serve_boundary(boundary_id):
    record = db.session.get(BoundaryRecord, boundary_id)
    if record is None:
        abort(404)
    if record.parcel.user_id != current_user.id and current_user.role != "admin":
        abort(403)
    return _send_project_file(record.boundary_file, current_app.config["BOUNDARY_FOLDER"])


@media_bp.route("/media/artifact/<int:analysis_id>/<key>")
@login_required
def serve_artifact(analysis_id, key):
    """Serve a generated output (heatmap, mask, ...) for an owned analysis."""
    from routes.helpers import get_analysis_or_denied
    analysis = get_analysis_or_denied(analysis_id)
    artifacts = json.loads(analysis.artifacts or "{}")
    rel_path = artifacts.get(key)
    if not rel_path:
        abort(404)
    return _send_project_file(rel_path, Path(current_app.config["OUTPUT_FOLDER"]))
