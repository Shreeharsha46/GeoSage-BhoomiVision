"""
GeoSage - Database models.

Seven relational tables cover the complete pipeline:

  users            -> registered analysts / administrators
  land_parcels     -> monitored land parcels (optionally georeferenced)
  land_images      -> old & recent satellite/drone images per parcel
  analysis_results -> one row per image-comparison run
  detected_regions -> changed regions found by the CV engine
  boundary_records -> uploaded GeoJSON/KML boundary files
  review_records   -> human verification audit trail

All foreign keys follow the design in the project specification.
"""
from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import db


def utcnow():
    """Timezone-aware UTC timestamp (naive utcnow() is deprecated)."""
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    """Registered user. Two demo roles: 'admin' and 'analyst'."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="analyst")
    # Column attribute shadows UserMixin's `is_active` property on purpose:
    # Flask-Login then honours deactivated accounts.
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    parcels = db.relationship(
        "LandParcel", backref="owner", lazy=True, cascade="all, delete-orphan"
    )
    reviews = db.relationship("ReviewRecord", backref="reviewer", lazy=True)

    # --- Password helpers (hashing handled by Werkzeug) -------------------
    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class LandParcel(db.Model):
    """A monitored land parcel.

    Latitude/longitude and CRS are optional: when location metadata is
    missing the parcel stays in image space and is clearly marked as
    'not georeferenced' everywhere in the UI.
    """
    __tablename__ = "land_parcels"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    parcel_name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(255))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    coordinate_reference_system = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    images = db.relationship(
        "LandImage", backref="parcel", lazy=True, cascade="all, delete-orphan"
    )
    analyses = db.relationship(
        "AnalysisResult", backref="parcel", lazy=True, cascade="all, delete-orphan"
    )
    boundaries = db.relationship(
        "BoundaryRecord", backref="parcel", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def is_georeferenced(self):
        """True only when usable coordinates exist (never invented)."""
        return self.latitude is not None and self.longitude is not None

    def __repr__(self):
        return f"<LandParcel {self.parcel_name}>"


class LandImage(db.Model):
    """One uploaded satellite/drone image belonging to a parcel."""
    __tablename__ = "land_images"

    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(
        db.Integer, db.ForeignKey("land_parcels.id"), nullable=False, index=True
    )
    image_path = db.Column(db.String(500), nullable=False)
    image_date = db.Column(db.Date)                      # capture date supplied by the user
    image_type = db.Column(db.String(20), nullable=False, default="old")   # 'old' | 'recent'
    # NOTE: `metadata` is a reserved attribute name in SQLAlchemy's
    # declarative base, so the Python attribute is `image_metadata` while
    # the database column keeps the specification's name `metadata`.
    image_metadata = db.Column("metadata", db.Text)

    def __repr__(self):
        return f"<LandImage {self.image_path} ({self.image_type})>"


class AnalysisResult(db.Model):
    """One run of the AI image-comparison engine for a parcel."""
    __tablename__ = "analysis_results"

    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(
        db.Integer, db.ForeignKey("land_parcels.id"), nullable=False, index=True
    )
    old_image_id = db.Column(db.Integer, db.ForeignKey("land_images.id"), nullable=False)
    new_image_id = db.Column(db.Integer, db.ForeignKey("land_images.id"), nullable=False)
    change_percentage = db.Column(db.Float)
    analysis_date = db.Column(db.DateTime, default=utcnow, nullable=False)
    processing_method = db.Column(db.String(100))
    result_summary = db.Column(db.Text)
    # --- extended fields (added in later stages, applied by migrations) ---
    processing_metadata = db.Column(db.Text)   # JSON: registration/quality stats
    artifacts = db.Column(db.Text)             # JSON: paths of generated outputs
    review_priority = db.Column(db.String(10)) # overall low/medium/high or 'insufficient_data'
    boundary_summary = db.Column(db.Text)      # JSON: latest boundary comparison

    old_image = db.relationship("LandImage", foreign_keys=[old_image_id])
    new_image = db.relationship("LandImage", foreign_keys=[new_image_id])
    regions = db.relationship(
        "DetectedRegion", backref="analysis", lazy=True, cascade="all, delete-orphan"
    )
    reviews = db.relationship(
        "ReviewRecord", backref="analysis", lazy=True, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<AnalysisResult #{self.id} change={self.change_percentage}%>"


class DetectedRegion(db.Model):
    """A changed region found by the CV engine inside one analysis.

    `confidence` is filled only when a model produces a meaningful score;
    classical CV results carry a detection-quality indicator instead.
    `priority` (low/medium/high) is an AI-generated *review* priority,
    never proof of illegal encroachment.
    """
    __tablename__ = "detected_regions"

    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(
        db.Integer, db.ForeignKey("analysis_results.id"), nullable=False, index=True
    )
    region_type = db.Column(db.String(50))
    pixel_area = db.Column(db.Integer)
    geographic_area = db.Column(db.Float)   # filled only with a valid CRS + scale
    confidence = db.Column(db.Float)
    priority = db.Column(db.String(10))     # 'low' | 'medium' | 'high'
    explanation = db.Column(db.Text)        # generated from actual processing results
    # --- extended fields (Stage 3+) ---
    bbox = db.Column(db.Text)               # JSON [x1, y1, x2, y2] in image pixels
    centroid = db.Column(db.Text)           # JSON [cx, cy] in image pixels
    mean_intensity = db.Column(db.Float)    # mean difference intensity inside region
    detection_method = db.Column(db.String(50))

    def __repr__(self):
        return f"<DetectedRegion {self.region_type} ({self.priority})>"


class BoundaryRecord(db.Model):
    """A boundary polygon attached to a parcel (Stage 4).

    Sources:
      'upload'   - user-provided GeoJSON/KML file (geographic space),
      'manual'   - polygon drawn in the UI (geographic or image space),
      'detected' - candidate polygon from classical image boundary
                   detection (image space; NEVER a legal boundary).

    `space` is 'geographic' (EPSG:4326 lon/lat) or 'image' (pixels).
    Comparisons are only ever computed between records of the SAME space.
    """
    __tablename__ = "boundary_records"

    id = db.Column(db.Integer, primary_key=True)
    parcel_id = db.Column(
        db.Integer, db.ForeignKey("land_parcels.id"), nullable=False, index=True
    )
    boundary_file = db.Column(db.String(500))
    geometry_type = db.Column(db.String(50))
    coordinate_reference_system = db.Column(db.String(50))
    # --- extended fields (Stage 4, applied by migrations) ---
    source = db.Column(db.String(20), default="upload")
    space = db.Column(db.String(20), default="geographic")
    geometry_json = db.Column(db.Text)      # ring coordinates [[x,y], ...]
    label = db.Column(db.String(120))       # user-visible name of the polygon
    comparison_json = db.Column(db.Text)    # last comparison/screening result

    def __repr__(self):
        return f"<BoundaryRecord {self.boundary_file}>"


class ReviewRecord(db.Model):
    """Human verification audit trail (Innovation 8: Human Verification System)."""
    __tablename__ = "review_records"

    STATUS_PENDING = "pending_verification"
    STATUS_VERIFIED = "verified_by_reviewer"
    STATUS_REJECTED = "rejected_false_detection"

    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(
        db.Integer, db.ForeignKey("analysis_results.id"), nullable=False, index=True
    )
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    review_status = db.Column(db.String(40), nullable=False, default=STATUS_PENDING)
    previous_status = db.Column(db.String(40))  # audit trail: status before this decision
    comments = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def __repr__(self):
        return f"<ReviewRecord {self.review_status}>"


class LandUseObservation(db.Model):
    """Classical land-use baseline proportions for one analysis (Stage 5).

    These are heuristic computer-vision observations, explicitly NOT a
    trained machine-learning classifier output.
    """
    __tablename__ = "land_use_observations"

    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(
        db.Integer, db.ForeignKey("analysis_results.id"), nullable=False, index=True
    )
    category = db.Column(db.String(30), nullable=False)  # vegetation/agriculture/builtup/bare_soil/water
    old_proportion = db.Column(db.Float)                 # 0..1 share in previous image
    new_proportion = db.Column(db.Float)                 # 0..1 share in recent image
    delta_proportion = db.Column(db.Float)               # new - old
