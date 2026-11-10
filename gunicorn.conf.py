"""
Gunicorn configuration for GeoSage production deployment.

Optimized for memory-constrained environments (free hosting tiers).
Adjust workers/threads based on available memory.
"""

import os

# Bind to port from environment (Render sets PORT)
bind = f"0.0.0.0:{os.environ.get('PORT', 8000)}"

# Worker configuration
# For memory-constrained environments, use fewer workers with threads
workers = int(os.environ.get("WEB_CONCURRENCY", 1))
threads = int(os.environ.get("WEB_THREADS", 4))

# Worker class - gthread for I/O bound applications
worker_class = "gthread"

# Worker timeouts (seconds)
timeout = 120
graceful_timeout = 30

# Keep-alive connections
keepalive = 5

# Max requests per worker before recycling (prevents memory leaks)
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

# Preload app for memory efficiency (but requires app to be fork-safe)
preload_app = False

# Worker temp directory (use /dev/shm for performance if available)
worker_tmp_dir = "/dev/shm"

# Security headers (handled by Flask app, but gunicorn can add some)
secure_scheme_headers = {"X-FORWARDED-PROTOCOL": "ssl", "X-FORWARDED-PROTO": "https", "X-FORWARDED-SSL": "on"}

# Limit request fields
limit_request_fields = 100
limit_request_field_size = 8190

# Pre-fork hook
def pre_fork(server, worker):
    """Called before forking a new worker."""
    pass

# Post-fork hook
def post_fork(server, worker):
    """Called after forking a new worker."""
    # Re-seed random, re-establish DB connections, etc.
    import random
    random.seed()

# Worker abort hook
def worker_abort(worker):
    """Called when worker aborts."""
    pass