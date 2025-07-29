# app/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# instâncias a usar na app
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
