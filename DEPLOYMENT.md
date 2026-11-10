# GeoSage — BHOOMI VISION Deployment Guide

## Overview

This guide covers deploying the GeoSage engineering mini-project to **Render** (free tier) with production-ready configuration.

## Prerequisites

- GitHub account
- Render account (free at render.com)
- Python 3.11+ locally for testing

## Files Created for Deployment

| File | Purpose |
|------|---------|
| `wsgi.py` | Production WSGI entry point |
| `gunicorn.conf.py` | Gunicorn configuration (memory-optimized) |
| `render.yaml` | Render Infrastructure-as-Code config |
| `Dockerfile` | Optional container deployment |
| `.dockerignore` | Exclude dev files from container builds |
| `modules/storage.py` | Cloud storage abstraction (S3/R2) |
| `config.py` | Updated with production settings |

## Quick Deploy to Render (Recommended)

### 1. Push to GitHub

```bash
cd path/to/GeoSage
git init
git add .
git commit -m "GeoSage deployment ready"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/geosage.git
git push -u origin main
```

### 2. Connect to Render

1. Go to [render.com](https://render.com) → **New +** → **Blueprint**
2. Connect your GitHub repository
3. Render will detect `render.yaml` automatically
4. Click **Apply** to create the service

### 3. Configure Environment Variables (Required)

In **Render Dashboard → Your Service → Environment**, add:

| Key | Value | Required |
|-----|-------|----------|
| `SECRET_KEY` | Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` | **YES** |
| `FLASK_CONFIG` | `production` | Auto-set via render.yaml |
| `DATABASE_URL` | (Optional) PostgreSQL URL if using DB addon | For persistent data |

### 4. Optional: Add PostgreSQL Database (Free Tier)

In Render Dashboard → **New +** → **PostgreSQL**:
- Name: `geosage-db`
- Plan: Free
- Copy the **Internal Database URL** to `DATABASE_URL` env var

### 5. Optional: Persistent File Storage

Render free tier has **ephemeral filesystem** — uploaded files lost on deploy.

For persistent uploads/outputs, configure **S3-compatible storage**:

| Env Var | Example Value |
|---------|---------------|
| `STORAGE_BACKEND` | `s3` |
| `AWS_S3_BUCKET` | `my-geosage-bucket` |
| `AWS_REGION` | `us-east-1` |
| `AWS_ACCESS_KEY_ID` | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | `...` |
| `S3_ENDPOINT_URL` | `https://<account>.r2.cloudflarestorage.com` (for Cloudflare R2) |

> **Recommendation**: Cloudflare R2 has **zero egress fees** and generous free tier (10 GB/mo).

## Local Production Testing

```bash
# Test production config with Flask test client
FLASK_CONFIG=production python -c "
from app import create_app
app = create_app('production')
with app.test_client() as c:
    print(c.get('/health').get_json())
    print('Home:', c.get('/').status_code)
"
```

## Key Configuration Changes for Production

| Setting | Development | Production |
|---------|-------------|------------|
| `DEBUG` | `True` | `False` |
| `SEED_DEMO_USERS` | `True` | `False` |
| `WTF_CSRF_ENABLED` | `True` | `True` |
| `SECRET_KEY` | dev default | **Must set via env** |
| `SQLALCHEMY_DATABASE_URI` | Local SQLite | Env `DATABASE_URL` |
| `SEED_DEMO_USERS` | `True` | `False` |

## Render Free Tier Limitations ⚠️

| Resource | Limit | Impact on GeoSage |
|----------|-------|-------------------|
| **RAM** | 512 MB | Tight for OpenCV + GeoPandas; use 1 worker |
| **CPU** | Shared | Image processing may be slow |
| **Filesystem** | Ephemeral | **Files lost on deploy** — use S3/R2 |
| **Spin-down** | 15 min inactivity | Cold start ~30 seconds |
| **Custom Domain** | Paid plan only | Use `*.onrender.com` subdomain |
| **Build Time** | 15 min max | May timeout on heavy deps |
| **Outbound Requests** | Allowed | OK for external APIs (none used) |

### Memory Optimization Tips

- `gunicorn.conf.py` uses **1 worker + 4 threads** (low memory)
- `MAX_ANALYSIS_WIDTH = 1600` limits image processing memory
- `opencv-python-headless` saves ~20 MB vs full OpenCV
- Consider upgrading to **Starter plan ($7/mo)** for 1 GB RAM if needed

## Alternative: Deploy with Docker

```bash
# Build locally
docker build -t geosage .

# Run locally
docker run -p 8000:8000 \
  -e SECRET_KEY=your-secret \
  -e FLASK_CONFIG=production \
  geosage
```

> Note: Render native Python is preferred over Docker on free tier (faster builds, no Docker layer limits).

## Post-Deployment Verification

After deploy, verify these endpoints work:

| Endpoint | Expected |
|----------|----------|
| `GET /health` | `{"status":"ok","app":"GeoSage"}` |
| `GET /` | Landing page loads |
| `GET /login` | Login form |
| `POST /register` | Creates account |
| `GET /dashboard` | Redirects to login |
| `GET /analysis/new` | Analysis form |
| `GET /boundaries/` | Boundary management |
| `GET /history/` | Timeline view |
| `GET /landuse/` | Land-use monitoring |
| `GET /reviews/` | Verification queue |
| `GET /reports/` | Report downloads |
| `GET /assistant/` | AI assistant |
| `GET /admin/users` | Admin panel (admin only) |
| `GET /settings/` | User settings |

## Security Checklist ✅

- [ ] `SECRET_KEY` set to strong random value (32+ bytes)
- [ ] `DEBUG = False` in production
- [ ] `WTF_CSRF_ENABLED = True`
- [ ] `SEED_DEMO_USERS = False` in production
- [ ] Strong passwords enforced (8+ chars, letter + digit)
- [ ] Upload validation (type, size, content sniffing)
- [ ] Path traversal protection in file serving
- [ ] Session cookies: HttpOnly, Secure (HTTPS)
- [ ] Passwords hashed with Werkzeug (PBKDF2)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Build fails on `rasterio`/`gdal` | Render installs system deps automatically; check build logs |
| Memory limit exceeded | Reduce `MAX_ANALYSIS_WIDTH`, use 1 gunicorn worker |
| Files disappear after deploy | Configure S3/R2 storage backend |
| Cold start timeout | Upgrade to paid plan or accept 30s delay |
| `SECRET_KEY` warning | Set strong random value in Render env vars |
| Database locked errors | Use PostgreSQL (SQLite not for concurrent writes) |

## Cost Summary

| Component | Free Tier | Paid Upgrade |
|-----------|-----------|--------------|
| Web Service | Free (512 MB RAM) | $7/mo (1 GB RAM) |
| PostgreSQL | Free (90 MB, 7-day backup) | $7/mo (1 GB) |
| Custom Domain | ❌ | $10/mo (or bring own) |
| Cloudflare R2 | 10 GB/mo free | $0.015/GB/mo |

## Conclusion

GeoSage is ready for Render deployment. The free tier works for **demonstration purposes** with the caveats above. For persistent file storage and better performance, add Cloudflare R2 storage and consider the Starter plan.

**Estimated deploy time**: 5-10 minutes after pushing to GitHub.

---

*For questions or issues, check Render docs: https://render.com/docs/deploy-flask*