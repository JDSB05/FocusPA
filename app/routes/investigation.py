from flask import Blueprint
from flask_login import login_required
from ..controllers import investigation_controller

investigation_bp = Blueprint('investigation', __name__, url_prefix='/investigations')

# Rotas existentes
investigation_bp.route('/', endpoint='list')(login_required(investigation_controller.list_investigations))
investigation_bp.route('/dropdown', endpoint='dropdown')(login_required(investigation_controller.investigation_dropdown))
investigation_bp.route('/start/<int:anomaly_id>', methods=['POST'], endpoint='start')(login_required(investigation_controller.start_investigation))
investigation_bp.route('/<int:id>', endpoint='detail')(login_required(investigation_controller.investigation_detail))
investigation_bp.route('/<int:id>/complete', methods=['POST'], endpoint='complete')(login_required(investigation_controller.complete_investigation))

# Novas rotas para anomalias
investigation_bp.route('/<int:inv_id>/remove_anomaly/<int:anomaly_id>', methods=['POST'], endpoint='remove_anomaly')(login_required(investigation_controller.remove_anomaly))
investigation_bp.route('/<int:inv_id>/add_anomaly/<int:anomaly_id>', methods=['POST'], endpoint='add_anomaly')(login_required(investigation_controller.add_anomaly))

# Novas rotas para ficheiros
investigation_bp.route('/<int:inv_id>/upload_file', methods=['POST'], endpoint='upload_file')(login_required(investigation_controller.upload_file))
investigation_bp.route('/<int:inv_id>/delete_file/<int:file_id>', methods=['POST'], endpoint='delete_file')(login_required(investigation_controller.delete_file))
investigation_bp.route('/<int:inv_id>/download_file/<int:file_id>', methods=['GET'], endpoint='download_file')(login_required(investigation_controller.download_file))

#Novas rotas para notas
investigation_bp.route('/<int:inv_id>/notes/add', methods=['POST'], endpoint='add_note')(login_required(investigation_controller.add_note))
investigation_bp.route('/<int:inv_id>/notes/delete/<int:note_id>', methods=['POST'], endpoint='delete_note')(login_required(investigation_controller.delete_note))
