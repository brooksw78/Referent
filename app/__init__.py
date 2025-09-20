from flask import Flask
from .db import init_db
from .routes import bp as main_bp

def create_app():
    app = Flask(__name__)
    init_db()
    app.register_blueprint(main_bp)
    return app