import os

from flask import Flask

from .db import init_db
from .routes import bp as main_bp

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    init_db()
    app.register_blueprint(main_bp)
    return app
