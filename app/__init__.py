# app/__init__.py

from datetime import timedelta, datetime
import os
from pathlib import Path
from flask import Flask, jsonify, redirect, request, session, url_for
from flask_login import current_user
from apscheduler.schedulers.background import BackgroundScheduler

from app.controllers.rag_controller import ask_llm, ask_llm_stream, delete_think_stream
from app.utils.others import ensure_model
from .services.anomaly_service import detect_and_create_anomalies
from .services.elastic import create_fake_winlogs
from .config import Config
from .extensions import db, login_manager, migrate
from .routes import (
    main_bp,
    auth_bp,
    policy_bp,
    security_policy_bp,
    anomaly_bp,
    investigation_bp,
    accesslog_bp,
    rag_bp,
    log_bp,
)
from .model import Anomaly, User, create_test_anomalies, create_investigation
from dotenv import load_dotenv

if (load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))):
    print("[INFO] .env file loaded successfully")
else:
    print("[WARNING] No .env file found in the directory: ", os.path.dirname(__file__))

LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-r1")
LLM_MODEL_LIGHT = os.getenv("LLM_MODEL_LIGHT", "deepseek-coder-v2")

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
    
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({"error": "Not authenticated"}), 401
        return redirect(url_for('auth.login'))


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
    app.register_blueprint(security_policy_bp)
    app.register_blueprint(anomaly_bp)
    app.register_blueprint(investigation_bp)
    app.register_blueprint(accesslog_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(log_bp)

    # Cria tabelas se não existirem
    with app.app_context():
        db.create_all()
        #create_test_anomalies()
        ensure_model(LLM_MODEL)
        ensure_model(LLM_MODEL_LIGHT)
        # Garante que existe um utilizador admin
        user = User.query.get(1)
        if not user:
            user = User(username="admin", email="admin@example.com")
            user.set_password("admin123")
            db.session.add(user)
            db.session.commit()
            print(f"Utilizador admin criado com id={user.id}")
        else:
            print(f"Utilizador admin já existe com id={user.id}")

        # Criar investigação associada às primeiras 3 anomalias
        anomaly_ids = [a.id for a in Anomaly.query.limit(3).all()]
        #investigation = create_investigation(
        #    description="Análise aprofundada de padrões anómalos vindos do cluster ES.",
        #    anomaly_ids=anomaly_ids,
        #    responsible_id=1  # opcional, ID do user responsável
        #)

        #print(investigation)
        #print(investigation.anomalies)  # lista de anomalias ligadas

    #create_fake_winlogs()
    # Scheduler para deteção automática
    scheduler = BackgroundScheduler()

    # Envolve a chamada no app_context para não perder o contexto
    def job_wrapper():
        with app.app_context():
            detect_and_create_anomalies()

    scheduler.add_job(job_wrapper, 'interval', minutes=5, id='detect_anomalies', replace_existing=False, max_instances=1, next_run_time=datetime.now() + timedelta(seconds=10))
    #scheduler.start() # Descomente para ativar o scheduler

    return app
