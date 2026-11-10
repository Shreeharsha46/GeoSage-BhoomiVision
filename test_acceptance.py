from app import create_app
from database.db import db
from database.models import User, LandParcel, LandImage, AnalysisResult, DetectedRegion, ReviewRecord, BoundaryRecord
from PIL import Image
import io, numpy as np, cv2

def make_textured(seed, size=(600,800)):
    rng = np.random.default_rng(seed)
    img = np.zeros((size[0], size[1], 3), np.uint8)
    img[:] = (40, 110, 60)
    for _ in range(300):
        x, y = rng.integers(0, size[1]-60), rng.integers(0, size[0]-60)
        w, h = rng.integers(15, 60), rng.integers(15, 60)
        color = tuple(int(c) for c in rng.integers(20, 200, 3))
        cv2.rectangle(img, (x, y), (x+w, y+h), color, -1)
    buf = io.BytesIO()
    Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(buf, format='PNG')
    return buf.getvalue()

app = create_app('testing')
with app.app_context():
    db.create_all()
    analyst = User(name='Test Analyst', email='analyst@geosage.test', role='analyst')
    analyst.set_password('Analyst@1234')
    admin = User(name='Test Admin', email='admin@geosage.test', role='admin')
    admin.set_password('Admin@1234')
    db.session.add_all([analyst, admin])
    db.session.commit()

client = app.test_client()

# ===== 1. REGISTER NEW USER =====
print('1. REGISTER NEW USER')
r = client.post('/register', data={'name': 'Test User', 'email': 'test@example.com', 'password': 'TestPass123', 'confirm': 'TestPass123'}, follow_redirects=True)
assert r.status_code == 200
print('   + Registration successful')

# ===== 2. LOGIN =====
print('2. LOGIN')
r = client.post('/login', data={'email': 'test@example.com', 'password': 'TestPass123'}, follow_redirects=True)
assert r.status_code == 200
print('   + Login successful')

# ===== 3. CREATE PARCEL =====
print('3. CREATE PARCEL')
r = client.post('/parcels/new', data={'parcel_name': 'Test Field', 'location': 'Village 5', 'latitude': '15.50', 'longitude': '75.20', 'coordinate_reference_system': 'EPSG:4326'}, follow_redirects=True)
assert r.status_code == 200
assert b'Test Field' in r.data
print('   + Parcel created')

with app.app_context():
    parcel = db.session.query(LandParcel).filter_by(parcel_name='Test Field').first()
    pid = parcel.id

# ===== 4. UPLOAD IMAGES =====
print('4. UPLOAD IMAGES')
old = make_textured(42)
old_arr = np.frombuffer(old, np.uint8)
old_img = cv2.imdecode(old_arr, cv2.IMREAD_COLOR)
M = np.float32([[1, 0, 5], [0, 1, 3]])
recent_img = cv2.warpAffine(old_img, M, (800, 600))
cv2.rectangle(recent_img, (300, 200), (450, 320), (90, 90, 200), -1)
buf = io.BytesIO()
Image.fromarray(cv2.cvtColor(recent_img, cv2.COLOR_BGR2RGB)).save(buf, format='PNG')
recent = buf.getvalue()

r = client.post(f'/parcels/{pid}/images', data={'image': (io.BytesIO(old), 'old.png'), 'image_type': 'old', 'image_date': '2024-01-01'}, content_type='multipart/form-data', follow_redirects=True)
assert b'Image added' in r.data
r = client.post(f'/parcels/{pid}/images', data={'image': (io.BytesIO(recent), 'new.png'), 'image_type': 'recent', 'image_date': '2024-06-01'}, content_type='multipart/form-data', follow_redirects=True)
assert b'Image added' in r.data
print('   + Images uploaded')

# ===== 5. RUN ANALYSIS =====
print('5. RUN ANALYSIS')
r = client.post('/analysis/new', data={'parcel_id': pid}, follow_redirects=True)
assert r.status_code == 200
with app.app_context():
    analysis = db.session.query(AnalysisResult).filter_by(parcel_id=pid).first()
    aid = analysis.id
    print(f'   + Analysis #{aid} created')
    print(f'      Change: {analysis.change_percentage}%')
    print(f'      Priority: {analysis.review_priority}')
    print(f'      Regions: {len(analysis.regions)}')

# ===== 6. BOUNDARY UPLOAD =====
print('6. BOUNDARY UPLOAD')
geojson = '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[75.10,15.50],[75.12,15.50],[75.12,15.52],[75.10,15.52],[75.10,15.50]]]}}]}'
r = client.post('/boundaries/upload', data={'parcel_id': pid, 'boundary_file': (io.BytesIO(geojson.encode()), 'boundary.geojson')}, content_type='multipart/form-data', follow_redirects=True)
assert r.status_code == 200
print('   + Boundary uploaded')

# ===== 7. DETECT CANDIDATE BOUNDARIES =====
print('7. DETECT CANDIDATE BOUNDARIES')
with app.app_context():
    image = db.session.query(LandImage).filter_by(parcel_id=pid).first()
    iid = image.id
r = client.post(f'/boundaries/parcel/{pid}/detect', data={'image_id': iid}, follow_redirects=True)
assert r.status_code == 200
print('   + Candidate boundaries detected')

# ===== 8. COMPARE BOUNDARIES =====
print('8. COMPARE BOUNDARIES')
with app.app_context():
    recorded = db.session.query(BoundaryRecord).filter_by(parcel_id=pid, source='upload').first()
    candidate = db.session.query(BoundaryRecord).filter_by(parcel_id=pid, source='detected').first()
r = client.post(f'/boundaries/parcel/{pid}/compare', data={'recorded_id': recorded.id, 'candidate_id': candidate.id}, follow_redirects=True)
assert r.status_code == 200
print('   + Boundaries compared')

# ===== 9. VIEW ANALYSIS DETAIL =====
print('9. VIEW ANALYSIS DETAIL')
r = client.get(f'/analysis/{aid}')
assert r.status_code == 200
assert b'Region 1' in r.data
print('   + Analysis detail view works')

# ===== 10. DOWNLOAD PDF REPORT =====
print('10. DOWNLOAD PDF REPORT')
r = client.get(f'/reports/{aid}/download')
assert r.status_code == 200
assert r.headers['Content-Type'] == 'application/pdf'
assert len(r.data) > 100000
print('   + PDF report generated')

# ===== 11. AI ASSISTANT =====
print('11. AI ASSISTANT QUERIES')
r = client.post('/assistant/ask', data={'analysis_id': aid, 'question': 'what changes were detected'}, follow_redirects=True)
assert r.status_code == 200
data = r.get_json()
assert 'answer' in data
assert 'visual change' in data['answer'].lower()
print('   + "what changes" works')

r = client.post('/assistant/ask', data={'analysis_id': aid, 'question': 'why was region 1 flagged'}, follow_redirects=True)
data = r.get_json()
assert 'answer' in data
print('   + "why region 1" works')

r = client.post('/assistant/ask', data={'analysis_id': aid, 'question': 'is this result legally verified'}, follow_redirects=True)
data = r.get_json()
assert 'answer' in data
assert 'verified' in data['answer'].lower() or 'verification' in data['answer'].lower()
print('   + "legally verified" works')

# ===== 12. VERIFICATION WORKFLOW (ADMIN) =====
print('12. VERIFICATION WORKFLOW')
# Use admin client for verification
admin_client = app.test_client()
admin_client.post('/login', data={'email': 'admin@geosage.test', 'password': 'Admin@1234'}, follow_redirects=True)
r = admin_client.post(f'/reviews/{aid}/record', data={'status': 'verified_by_reviewer', 'comments': 'Confirmed on ground'}, follow_redirects=True)
assert r.status_code == 200
with app.app_context():
    review = db.session.query(ReviewRecord).filter_by(analysis_id=aid).order_by(ReviewRecord.id.desc()).first()
    assert review.review_status == 'verified_by_reviewer'
print('   + Verification recorded')

# ===== 13. HISTORICAL TIMELINE =====
print('13. HISTORICAL TIMELINE')
r = client.get('/history/')
assert r.status_code == 200
print('   + Timeline view works')

# ===== 14. SECURITY: CROSS-USER ACCESS PREVENTION =====
print('14. CROSS-USER ACCESS PREVENTION')
# Use a new client for user2 (the test user we registered)
client2 = app.test_client()
client2.post('/login', data={'email': 'test@example.com', 'password': 'TestPass123'}, follow_redirects=True)
with app.app_context():
    user2 = db.session.query(User).filter_by(email='test@example.com').first()
    other_parcel = LandParcel(owner=user2, parcel_name='Other User Parcel')
    db.session.add(other_parcel)
    db.session.commit()
    oid = other_parcel.id

# Now create a parcel for the analyst user
with app.app_context():
    analyst = db.session.query(User).filter_by(email='analyst@geosage.test').first()
    other_parcel = LandParcel(owner=analyst, parcel_name='Analyst Parcel')
    db.session.add(other_parcel)
    db.session.commit()
    pid_analyst = other_parcel.id

# Try to access analyst's parcel as test user
r = client2.get(f'/parcels/{pid_analyst}')
assert r.status_code == 403
print('   + Cross-user parcel access prevented')

# ===== 15. SECURITY: PROTECTED ROUTES =====
print('15. PROTECTED ROUTES')
client.get('/logout')
for path in ['/dashboard', '/parcels/', '/analysis/new', '/settings/']:
    r = client.get(path)
    assert r.status_code == 302
    assert '/login' in r.headers.get('Location', '')
print('   + Protected routes redirect to login')

print()
print('=' * 60)
print('ALL END-TO-END ACCEPTANCE CRITERIA PASSED')
print('=' * 60)