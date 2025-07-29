
from datetime import timedelta
from flask import Flask, session
from flask_login import current_user

from .config import Config
fr,  .extensions import db, login_manager, migrate
from .routes import main_bp, auth_bp
from .model import User



def create_app(config_class: type = Config) -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    setattr(login_manager, 'login_view', 'auth.login')

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    app.permanent_session_lifetime = timedelta(minutes=30)

    @app.before_request
    def refresh_session():
        if current_user.is_authenticated:
            session.permanent = True

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    # Criar tabelas se não existirem
    with app.app_context():
        db.create_all()

    return app
