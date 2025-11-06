import os
import secrets
import hmac
from pathlib import Path
from urllib.parse import urlparse, urljoin

from flask import (
    Flask,
    session,
    request,
    abort,
    redirect,
    url_for,
    flash,
    render_template,
)
from markupsafe import Markup

from .db import init_db
from .routes import bp as main_bp

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["LOGIN_USERNAME"] = os.environ.get("APP_LOGIN_USERNAME") or os.environ.get("BASIC_AUTH_USERNAME")
    app.config["LOGIN_PASSWORD"] = os.environ.get("APP_LOGIN_PASSWORD") or os.environ.get("BASIC_AUTH_PASSWORD")
    app.config["LOGIN_PAGE_TITLE"] = os.environ.get("APP_LOGIN_TITLE", "Sign in to Referent")
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

    def _login_enabled():
        return bool(app.config.get("LOGIN_USERNAME")) and bool(app.config.get("LOGIN_PASSWORD"))

    def _check_credentials(username, password):
        expected_username = app.config.get("LOGIN_USERNAME") or ""
        expected_password = app.config.get("LOGIN_PASSWORD") or ""
        return hmac.compare_digest(username or "", expected_username) and hmac.compare_digest(password or "", expected_password)

    def _is_safe_redirect(target):
        if not target:
            return False
        ref_url = urlparse(request.host_url)
        test_url = urlparse(urljoin(request.host_url, target))
        return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc

    def _redirect_target():
        for candidate in (request.form.get("next"), request.args.get("next")):
            if candidate and _is_safe_redirect(candidate):
                return candidate
        return url_for("main.index")

    @app.before_request
    def login_required():
        if not _login_enabled():
            return None
        endpoint = request.endpoint or ""
        if endpoint in {"login", "logout"}:
            return None
        if endpoint.startswith("static") or endpoint.endswith(".static"):
            return None
        if session.get("authenticated"):
            return None
        return redirect(url_for("login", next=request.url))

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

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not _login_enabled():
            abort(404)
        if session.get("authenticated"):
            return redirect(_redirect_target())

        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            if _check_credentials(username, password):
                session["authenticated"] = True
                flash("Signed in successfully.", "success")
                return redirect(_redirect_target())
            flash("Invalid username or password. Please try again.", "danger")

        next_url = request.args.get("next") if _is_safe_redirect(request.args.get("next")) else None
        return render_template(
            "login.html",
            next_url=next_url,
            login_title=app.config.get("LOGIN_PAGE_TITLE"),
        )

    @app.route("/logout")
    def logout():
        session.pop("authenticated", None)
        flash("Signed out.", "info")
        if not _login_enabled():
            return redirect(url_for("main.index"))
        return redirect(url_for("login"))

    @app.context_processor
    def inject_csrf_token():
        token = _generate_csrf_token()
        return {
            "csrf_token": token,
            "csrf_input": Markup(f'<input type="hidden" name="csrf_token" value="{token}">'),
        }

    return app
