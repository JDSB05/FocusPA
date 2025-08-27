# app/models.py
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email    = db.Column(db.String(120), unique=True, nullable=False)
    pwd_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    get_id = db.Column(db.String(80), unique=True, nullable=True)  # Optional field for user ID retrieval
    is_authenticated = db.Column(db.Boolean, default=True)  # Flask-Login compatibility

    def get_id(self):
        return str(self.id)  # Tem de devolver string
    
    def set_password(self, password):
        self.pwd_hash = generate_password_hash(password)

    def check_password(self, password):
        if self.pwd_hash is None:
            return False
        return check_password_hash(self.pwd_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"
    
    def delete_account(self):
        self.is_active = False
        self.pwd_hash = ""
        self.email = ""
        self.username = ""

class Policy(db.Model):
    __tablename__ = "policies"
    id = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(150), nullable=False)
    content     = db.Column(db.Text, nullable=False)  # JSON/YAML raw text of policy
    updated_at  = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    created_at  = db.Column(db.DateTime, default=datetime.now, index=True)
    
    def __repr__(self):
        return f"<Policy {self.name}>"

class Anomaly(db.Model):
    __tablename__ = "anomalies"
    id          = db.Column(db.Integer, primary_key=True)
    log_id      = db.Column(db.String(255), nullable=False) 
    timestamp   = db.Column(db.DateTime, default=datetime.now, index=True)
    source      = db.Column(db.String(120), nullable=False)   # ex. "elasticsearch", "chroma"
    description = db.Column(db.Text, nullable=False)
    severity    = db.Column(db.String(20), default="low")     # low, medium, high
    resolved    = db.Column(db.Boolean, default=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
    event_code  = db.Column(db.String(20), nullable=True, index=True)
    user        = db.Column(db.String(255), nullable=True, index=True)
    reasoning   = db.Column(db.Text, nullable=True)

    investigations = db.relationship(
        "Investigation",
        secondary="investigation_anomalies",
        back_populates="anomalies"
    )

    def mark_resolved(self):
        self.resolved = True
        self.resolved_at = datetime.now()

    def __repr__(self):
        return f"<Anomaly {self.id} sev={self.severity}>"

class Investigation(db.Model):
    __tablename__ = "investigations"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    state = db.Column(db.String(20), default="open")  # open, closed
    responsible_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    responsible = db.relationship("User", backref=db.backref("investigations", lazy="dynamic"))

    # ligação N:N com anomalias
    anomalies = db.relationship(
        "Anomaly",
        secondary="investigation_anomalies",
        back_populates="investigations"
    )

    def __repr__(self):
        return f"<Investigation {self.id} title={self.title} state={self.state}>"

investigation_anomalies = db.Table(
    "investigation_anomalies",
    db.Column("investigation_id", db.Integer, db.ForeignKey("investigations.id"), primary_key=True),
    db.Column("anomaly_id", db.Integer, db.ForeignKey("anomalies.id"), primary_key=True)
)

class Note(db.Model):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    investigation_id = db.Column(db.Integer, db.ForeignKey("investigations.id"), nullable=False)

    investigation = db.relationship("Investigation", backref=db.backref("notes", lazy="dynamic"))

class File(db.Model):
    __tablename__ = "files"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    data = db.Column(db.LargeBinary, nullable=False)  # armazena conteúdo binário
    mimetype = db.Column(db.String(50), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.now)
    investigation_id = db.Column(db.Integer, db.ForeignKey("investigations.id"), nullable=False)

    investigation = db.relationship("Investigation", backref=db.backref("files", lazy="dynamic"))

class AccessLog(db.Model):
    __tablename__ = "access_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    timestamp   = db.Column(db.DateTime, default=datetime.now, index=True)
    action      = db.Column(db.String(100), nullable=False)   # e.g. "login", "view_file"
    resource    = db.Column(db.String(255), nullable=True)    # ex. file path, endpoint
    ip_address  = db.Column(db.String(45), nullable=True)
    meta_info    = db.Column(db.JSON, nullable=True)           # armazena JSON extra (e.g. user agent)

    user = db.relationship("User", backref=db.backref("access_logs", lazy="dynamic"))

    def __repr__(self):
        return f"<AccessLog {self.action} by {self.user_id} at {self.timestamp}>"

def create_test_anomalies():
    """Função de teste para criar varias anomalias."""
    from random import choice, randint

    anomalies = []
    for _ in range(10):
        anomaly = Anomaly(
            log_id="test_log_" + str(randint(1, 1000)), # type: ignore
            source=choice(["elasticsearch", "chroma"]), # type: ignore
            description="Test anomaly description", # type: ignore
            severity=choice(["low", "medium", "high"]), # type: ignore
        )
        anomalies.append(anomaly)
    print("Test anomalies created")
    db.session.bulk_save_objects(anomalies)
    db.session.commit()

def create_investigation(title, description, anomaly_ids, responsible_id=None):
    """
    Cria uma nova investigação forense e associa anomalias existentes.
    
    :param title: Título da investigação
    :param description: Descrição da investigação
    :param anomaly_ids: Lista de IDs de anomalias a associar
    :param responsible_id: ID do utilizador responsável (opcional)
    :return: Investigation criada
    """
    # buscar anomalias da BD
    anomalies = Anomaly.query.filter(Anomaly.id.in_(anomaly_ids)).all()

    if not anomalies:
        raise ValueError("Nenhuma anomalia encontrada para os IDs fornecidos.")

    investigation = Investigation(
        title=title,
        description=description,
        responsible_id=responsible_id
    )

    # associar as anomalias à investigação
    investigation.anomalies.extend(anomalies)

    db.session.add(investigation)
    db.session.commit()

    print(f"Investigação '{title}' criada com {len(anomalies)} anomalias associadas.")
    return investigation