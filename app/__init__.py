import os
import secrets
import hmac
from pathlib import Path

from flask import Flask, session, request, abort
from markupsafe import Markup

from .db import init_db
from .routes import bp as main_bp

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config.setdefault("COVER_UPLOAD_SUBDIR", "uploads/covers")
    app.config.setdefault("ALLOWED_COVER_EXTENSIONS", {"png", "jpg", "jpeg", "gif", "webp"})
    app.config.setdefault("MAX_CONTENT_LENGTH", 4 * 1024 * 1024)  # 4 MB cap for uploads
    upload_folder = Path(app.static_folder) / app.config["COVER_UPLOAD_SUBDIR"]
    upload_folder.mkdir(parents=True, exist_ok=True)
    init_db()
    app.register_blueprint(main_bp)

    def _generate_csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

    @app.before_request
    def csrf_protect():
        if request.method not in SAFE_METHODS:
            token = session.get("_csrf_token")
            submitted = (
                request.form.get("csrf_token")
                or request.headers.get("X-CSRFToken")
                or request.headers.get("X-CSRF-Token")
            )
            if not token or not submitted or not hmac.compare_digest(token, submitted):
                abort(400)

    @app.context_processor
    def inject_csrf_token():
        token = _generate_csrf_token()
        return {
            "csrf_token": token,
            "csrf_input": Markup(f'<input type="hidden" name="csrf_token" value="{token}">'),
        }

    return app
