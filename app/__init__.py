# app/__init__.py

from datetime import timedelta, datetime
from flask import Flask, session
from flask_login import current_user
from apscheduler.schedulers.background import BackgroundScheduler
from .services.anomaly_service import detect_and_create_anomalies
from .config import Config
from .extensions import db, login_manager, migrate
from .routes import (
    main_bp,
    auth_bp,
    policy_bp,
    anomaly_bp,
    accesslog_bp,
    rag_bp,
)
from .model import User


def create_app(config_class: type = Config) -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializa extensões
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    setattr(login_manager, 'login_view', 'auth.login')

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    # Sessões permanentes
    app.permanent_session_lifetime = timedelta(minutes=30)

    @app.before_request
    def refresh_session():
        if current_user.is_authenticated:
            session.permanent = True

    # Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(policy_bp)
    app.register_blueprint(anomaly_bp)
    app.register_blueprint(accesslog_bp)
    app.register_blueprint(rag_bp)

    # Cria tabelas se não existirem
    with app.app_context():
        db.create_all()

    # Scheduler para deteção automática
    scheduler = BackgroundScheduler()

    # Envolve a chamada no app_context para não perder o contexto
    def job_wrapper():
        with app.app_context():
            detect_and_create_anomalies()

    scheduler.add_job(job_wrapper, 'interval', minutes=60, id='detect_anomalies', replace_existing=True, max_instances=1, next_run_time=datetime.now() + timedelta(seconds=10))
    scheduler.start() # Descomente para ativar o scheduler

    return app
