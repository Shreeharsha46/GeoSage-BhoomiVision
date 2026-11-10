"""
Stage 2 tests: image upload validation. Covers specification test items
10, 11, 12 and the security requirements (content sniffing, oversized
files, corrupt files, cross-user media access).
"""
import io

import pytest
from PIL import Image

from database.db import db
from database.models import LandImage, LandParcel, User


def make_png(width=200, height=150, color=(40, 110, 70)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def make_jpeg(width=200, height=150):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 90, 30)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def logged_in(app):
    client = app.test_client()
    client.post("/login", data={"email": "analyst@geosage.test", "password": "Analyst@1234"})
    with app.app_context():
        parcel = db.session.query(LandParcel).filter_by(
            parcel_name="Upload Parcel").first()
        if parcel is None:
            user = db.session.query(User).filter_by(email="analyst@geosage.test").first()
            parcel = LandParcel(owner=user, parcel_name="Upload Parcel")
            db.session.add(parcel)
            db.session.commit()
        parcel_id = parcel.id
    return client, parcel_id


def test_valid_image_upload(app, logged_in):
    client, parcel_id = logged_in
    response = client.post(f"/parcels/{parcel_id}/images", data={
        "image": (io.BytesIO(make_png()), "field.png"),
        "image_type": "old", "image_date": "2024-01-15",
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"Image added" in response.data
    with app.app_context():
        img = db.session.query(LandImage).filter_by(parcel_id=parcel_id).first()
        assert img is not None
        assert str(img.image_date) == "2024-01-15"
        # stored with a generated name - original filename never touches disk
        assert "field" not in img.image_path


def test_invalid_extension_rejected(logged_in):
    client, parcel_id = logged_in
    response = client.post(f"/parcels/{parcel_id}/images", data={
        "image": (io.BytesIO(b"not an image at all"), "malware.exe"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"Unsupported file type" in response.data


def test_disguised_file_rejected(logged_in):
    """A text file renamed to .png must be rejected by content sniffing."""
    client, parcel_id = logged_in
    response = client.post(f"/parcels/{parcel_id}/images", data={
        "image": (io.BytesIO(b"definitely not an image"), "fake.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"could not be decoded" in response.data


def test_extension_content_mismatch_rejected(logged_in):
    client, parcel_id = logged_in
    response = client.post(f"/parcels/{parcel_id}/images", data={
        "image": (io.BytesIO(make_jpeg()), "photo.png"),  # JPEG bytes, .png name
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"does not match" in response.data


def test_corrupt_image_rejected(logged_in):
    client, parcel_id = logged_in
    truncated = make_png()[:40]  # cut in the middle of the file
    response = client.post(f"/parcels/{parcel_id}/images", data={
        "image": (io.BytesIO(truncated), "broken.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"could not be decoded" in response.data or b"Unsupported" in response.data


def test_oversized_file_rejected(logged_in, monkeypatch):
    from routes import uploads
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 100)  # shrink limit for the test
    client, parcel_id = logged_in
    response = client.post(f"/parcels/{parcel_id}/images", data={
        "image": (io.BytesIO(make_png()), "big.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"larger than" in response.data


def test_tiny_image_rejected(logged_in):
    client, parcel_id = logged_in
    response = client.post(f"/parcels/{parcel_id}/images", data={
        "image": (io.BytesIO(make_png(10, 8)), "tiny.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert b"too small" in response.data


def test_media_route_permission_checked(app, logged_in):
    """Another user's image is never served through /media/image/<id>."""
    client, parcel_id = logged_in
    client.post(f"/parcels/{parcel_id}/images", data={
        "image": (io.BytesIO(make_png()), "mine.png"),
    }, content_type="multipart/form-data")

    with app.app_context():
        image_id = db.session.query(LandImage).first().id

    # anonymous request -> redirected to login
    anon = app.test_client()
    assert anon.get(f"/media/image/{image_id}").status_code == 302

    # a different analyst -> 403
    with app.app_context():
        stranger = User(name="Stranger", email="stranger@geosage.test", role="analyst")
        stranger.set_password("Stranger1")
        db.session.add(stranger)
        db.session.commit()
    other = app.test_client()
    other.post("/login", data={"email": "stranger@geosage.test", "password": "Stranger1"})
    assert other.get(f"/media/image/{image_id}").status_code == 403

    # owner -> 200 with image bytes
    assert client.get(f"/media/image/{image_id}").status_code == 200
