from flask import Blueprint
from flask_login import login_required

from ..controllers import anomaly_controller

anomaly_bp = Blueprint('anomaly', __name__, url_prefix='/anomalies')

anomaly_bp.route('/', endpoint='list_anomalies')(login_required(anomaly_controller.list_anomalies))
anomaly_bp.route('/<int:anomaly_id>', methods=['GET'], endpoint='get')(login_required(anomaly_controller.get_anomaly))
anomaly_bp.route('/', methods=['POST'], endpoint='create')(login_required(anomaly_controller.create_anomaly))
anomaly_bp.route('/<int:anomaly_id>', methods=['PUT', 'PATCH'], endpoint='update')(login_required(anomaly_controller.update_anomaly))
anomaly_bp.route('/<int:anomaly_id>/delete', methods=['POST'], endpoint='delete')(login_required(anomaly_controller.delete_anomaly))
