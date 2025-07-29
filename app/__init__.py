from flask import Flask
from .extensions import db
from .routes.main import main_bp

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SECRET_KEY'] = 'secret'
    db.init_app(app)
    with app.app_context():
        db.create_all()
    app.register_blueprint(main_bp)
    return app
