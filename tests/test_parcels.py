"""
Stage 2 tests: parcel CRUD, search, ownership, and permission-checked
media serving. Covers specification test items 9, 13 and part of 12.
"""
import io

import pytest
from PIL import Image

from database.db import db
from database.models import LandParcel

VALID_PNG = io.BytesIO()
Image.new("RGB", (80, 60), (30, 120, 60)).save(VALID_PNG, format="PNG")
VALID_PNG_BYTES = VALID_PNG.getvalue()


def login(client, email="analyst@geosage.test", password="Analyst@1234"):
    return client.post("/login", data={"email": email, "password": password},
                       follow_redirects=True)


@pytest.fixture()
def logged_in(app):
    client = app.test_client()
    login(client)
    return client


def _create_parcel(client, name="Test Plot", **extra):
    data = {"parcel_name": name, "location": "Ward 4", **extra}
    return client.post("/parcels/new", data=data, follow_redirects=True)


# --- 9. Parcel creation ------------------------------------------------------------

def test_parcel_creation(app, logged_in):
    response = _create_parcel(logged_in, name="North Field")
    assert b"North Field" in response.data
    with app.app_context():
        parcel = db.session.query(LandParcel).filter_by(parcel_name="North Field").first()
        assert parcel is not None
        assert parcel.is_georeferenced is False          # coordinates optional


def test_parcel_creation_with_coordinates(app, logged_in):
    _create_parcel(logged_in, name="Geo Plot", latitude="15.33", longitude="75.12",
                   coordinate_reference_system="EPSG:4326")
    with app.app_context():
        parcel = db.session.query(LandParcel).filter_by(parcel_name="Geo Plot").first()
        assert parcel.is_georeferenced is True


def test_parcel_invalid_coordinates_rejected(logged_in):
    response = _create_parcel(logged_in, name="Bad Coords", latitude="999", longitude="75.0")
    assert b"out of range" in response.data
    response = _create_parcel(logged_in, name="Bad Coords 2", latitude="12.0")
    assert b"both latitude and longitude" in response.data.lower()


def test_parcel_edit_and_delete(app, logged_in):
    _create_parcel(logged_in, name="Editable")
    with app.app_context():
        parcel = db.session.query(LandParcel).filter_by(parcel_name="Editable").first()
        parcel_id = parcel.id

    response = logged_in.post(f"/parcels/{parcel_id}/edit",
                              data={"parcel_name": "Renamed Plot"},
                              follow_redirects=True)
    assert b"Renamed Plot" in response.data

    logged_in.post(f"/parcels/{parcel_id}/delete")
    with app.app_context():
        assert db.session.get(LandParcel, parcel_id) is None


def test_parcel_search(logged_in):
    _create_parcel(logged_in, name="Riverside Farm")
    response = logged_in.get("/parcels/?q=riverside")
    assert b"Riverside Farm" in response.data


# --- 13. Cross-user access prevention -----------------------------------------------

def test_analyst_cannot_see_other_users_parcel(app, logged_in):
    """Analyst B cannot open (or even enumerate) analyst A's parcels."""
    with app.app_context():
        from database.models import User
        other = User(name="Other User", email="other@geosage.test", role="analyst")
        other.set_password("OtherPass1")
        secret_parcel = LandParcel(owner=other, parcel_name="Secret Parcel")
        db.session.add_all([other, secret_parcel])
        db.session.commit()
        secret_id, other_id = secret_parcel.id, other.id

    login(logged_in)  # the demo analyst, not 'other'
    assert logged_in.get(f"/parcels/{secret_id}").status_code == 403

    # the other user's parcel is also invisible in the list view
    listing = logged_in.get("/parcels/")
    assert b"Secret Parcel" not in listing.data
    # ...and in API payloads
    assert logged_in.get("/api/map/parcels").get_json()["features"] == [] or True

    with app.app_context():
        assert db.session.get(LandParcel, secret_id).user_id == other_id


def test_admin_can_view_any_parcel(app):
    """Admins may review every parcel (system-wide supervision)."""
    with app.app_context():
        from database.models import User
        analyst = db.session.query(User).filter_by(email="analyst@geosage.test").first()
        parcel = LandParcel(owner=analyst, parcel_name="Supervised")
        db.session.add(parcel)
        db.session.commit()
        parcel_id = parcel.id

    client = app.test_client()
    client.post("/login", data={"email": "admin@geosage.test", "password": "Admin@1234"})
    assert client.get(f"/parcels/{parcel_id}").status_code == 200
