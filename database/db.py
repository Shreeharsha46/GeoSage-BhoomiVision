"""
GeoSage - Database module.

`db` is the single SQLAlchemy instance shared by the whole application.
It is created without an app and later bound inside `create_app()`
(application-factory pattern), which lets tests spin up isolated apps.
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
