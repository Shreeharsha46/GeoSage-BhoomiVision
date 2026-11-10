"""
Stage 1 tests: application factory, database schema and model relationships.

Covers the specification's test items "database operations" and
"missing geospatial metadata" (parcels without coordinates must be
handled explicitly, never with invented coordinates).

Context discipline: every test pushes its own short-lived app context
for database work. A context must never span client requests, because
Flask-Login caches the authenticated user on the app context and it
would leak one client's login state into later requests.
"""
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from database.db import db
from database.models import (AnalysisResult, BoundaryRecord, DetectedRegion,
                             LandImage, LandParcel, ReviewRecord, User)

EXPECTED_TABLES = {
    "users", "land_parcels", "land_images", "analysis_results",
    "detected_regions", "boundary_records", "review_records",
}


def make_user(email="user1@geosage.test", role="analyst"):
    """Helper: a User with a properly hashed password."""
    user = User(name="Demo Analyst", email=email, role=role)
    user.set_password("S3curePass!")
    return user


# --- Schema -----------------------------------------------------------------

def test_all_spec_tables_created(app):
    """All seven tables from the specification exist in the database."""
    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
        assert EXPECTED_TABLES <= tables


def test_image_metadata_column_keeps_spec_name(app):
    """The spec's `metadata` column exists (Python attribute works around
    SQLAlchemy's reserved attribute name)."""
    assert "metadata" in LandImage.__table__.columns
    assert LandImage.__table__.columns["metadata"].name == "metadata"


# --- Users & passwords --------------------------------------------------------

def test_password_hashing(app):
    with app.app_context():
        user = make_user()
        db.session.add(user)
        db.session.commit()
        assert user.password_hash != "S3curePass!"      # never stored in plain text
        assert user.check_password("S3curePass!")
        assert not user.check_password("wrong-password")


def test_duplicate_email_rejected(app):
    with app.app_context():
        db.session.add(make_user())
        db.session.commit()
        db.session.add(make_user())                     # same email -> UNIQUE violation
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# --- Geospatial metadata handling ---------------------------------------------

def test_parcel_without_coordinates_is_not_georeferenced(app):
    """Missing geospatial metadata is explicit - coordinates are never invented."""
    with app.app_context():
        user = make_user()
        parcel = LandParcel(owner=user, parcel_name="Plot 7", location="Rural ward 3")
        db.session.add_all([user, parcel])
        db.session.commit()
        assert parcel.is_georeferenced is False
        assert parcel.coordinate_reference_system is None


def test_georeferenced_parcel(app):
    with app.app_context():
        user = make_user()
        parcel = LandParcel(owner=user, parcel_name="Plot 8", latitude=15.3173,
                            longitude=75.1232, coordinate_reference_system="EPSG:4326")
        db.session.add_all([user, parcel])
        db.session.commit()
        assert parcel.is_georeferenced is True


# --- Full relationship chain ----------------------------------------------------

def test_full_analysis_chain(app):
    """user -> parcel -> images -> analysis -> region -> review all link up."""
    with app.app_context():
        user = make_user()
        parcel = LandParcel(owner=user, parcel_name="Parcel A", latitude=15.3173,
                            longitude=75.1232, coordinate_reference_system="EPSG:4326")
        old_img = LandImage(parcel=parcel, image_path="uploads/old_images/old.jpg",
                            image_type="old")
        new_img = LandImage(parcel=parcel, image_path="uploads/recent_images/new.jpg",
                            image_type="recent")
        analysis = AnalysisResult(
            parcel=parcel, old_image=old_img, new_image=new_img,
            change_percentage=12.4, processing_method="ORB + differencing",
            result_summary="Moderate change concentrated near the north fence.",
        )
        region = DetectedRegion(
            analysis=analysis, region_type="possible_new_construction",
            pixel_area=4200, confidence=None, priority="medium",
            explanation="Pixel difference 12.4% concentrated in one connected cluster.",
        )
        review = ReviewRecord(analysis=analysis, reviewer=user,
                              review_status=ReviewRecord.STATUS_PENDING)
        db.session.add_all([user, parcel, old_img, new_img, analysis, region, review])
        db.session.commit()

        assert old_img.parcel.parcel_name == "Parcel A"
        assert analysis.old_image.image_type == "old"
        assert analysis.new_image.image_type == "recent"
        assert len(parcel.images) == 2
        assert len(parcel.analyses) == 1
        assert analysis.regions[0].priority == "medium"
        assert analysis.reviews[0].review_status == "pending_verification"
        assert user.reviews[0].reviewer.name == "Demo Analyst"


def test_boundary_record_link(app):
    with app.app_context():
        user = make_user()
        parcel = LandParcel(owner=user, parcel_name="Parcel B")
        boundary = BoundaryRecord(
            parcel=parcel, boundary_file="uploads/boundaries/sample.geojson",
            geometry_type="Polygon", coordinate_reference_system="EPSG:4326",
        )
        db.session.add_all([user, parcel, boundary])
        db.session.commit()
        assert parcel.boundaries[0].geometry_type == "Polygon"


# --- Cascade behaviour -----------------------------------------------------------

def test_cascade_delete_removes_children(app):
    """Deleting a parcel removes its images, analyses and detected regions."""
    with app.app_context():
        user = make_user()
        parcel = LandParcel(owner=user, parcel_name="Parcel C")
        old_img = LandImage(parcel=parcel, image_path="o.jpg", image_type="old")
        new_img = LandImage(parcel=parcel, image_path="n.jpg", image_type="recent")
        analysis = AnalysisResult(parcel=parcel, old_image=old_img,
                                  new_image=new_img, change_percentage=5.0)
        region = DetectedRegion(analysis=analysis, region_type="change", pixel_area=100)
        db.session.add_all([user, parcel, old_img, new_img, analysis, region])
        db.session.commit()

        db.session.delete(parcel)
        db.session.commit()

        assert db.session.query(LandImage).count() == 0
        assert db.session.query(AnalysisResult).count() == 0
        assert db.session.query(DetectedRegion).count() == 0


# --- Stage 1 HTTP endpoints --------------------------------------------------------

def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert resp.get_json()["app"] == "GeoSage"


def test_index_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Geo" in resp.data
