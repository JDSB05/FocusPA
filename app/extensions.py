# app/extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# instâncias a usar na app
db = SQLAlchemy()
migrate = Migrate()
