import os
from flask import Flask
from .extensions import db

def create_app():
    app = Flask(__name__)

    # ---- Aqui é onde "dizes" ao SQLAlchemy para usar o Postgres ----
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "postgresql://focuspa:123456@localhost:5432/focus_db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    return app