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
    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.String(255), unique=False, nullable=False) 
    timestamp   = db.Column(db.DateTime, default=datetime.now, index=True)
    source      = db.Column(db.String(120), nullable=False)   # ex. "elasticsearch", "chroma"
    description = db.Column(db.Text, nullable=False)
    severity    = db.Column(db.String(20), default="low")     # low, medium, high
    resolved    = db.Column(db.Boolean, default=False)
    resolved_at = db.Column(db.DateTime, nullable=True)

    def mark_resolved(self):
        self.resolved = True
        self.resolved_at = datetime.now()

    def __repr__(self):
        return f"<Anomaly {self.id} sev={self.severity}>"

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
    print("Test anomalies created:")
    for a in anomalies:
        print(f" - {a}")
    db.session.bulk_save_objects(anomalies)
    db.session.commit()
