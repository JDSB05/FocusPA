# app/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

from mcp_files.secure_mcp_client import SimpleAuthClient

# instâncias a usar na app
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mcp_client = SimpleAuthClient()