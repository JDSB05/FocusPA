from flask import Blueprint
from flask_login import login_required
from ..controllers import investigation_controller

investigation_bp = Blueprint('investigation', __name__, url_prefix='/investigations')

# Rotas
investigation_bp.route('/', endpoint='list')(login_required(investigation_controller.list_investigations))
investigation_bp.route('/start/<int:anomaly_id>', methods=['POST'], endpoint='start')(login_required(investigation_controller.start_investigation))
investigation_bp.route('/<int:id>', endpoint='detail')(login_required(investigation_controller.investigation_detail))
