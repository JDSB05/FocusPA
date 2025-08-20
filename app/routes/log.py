"""Blueprint de rotas para visualização de logs (ES) e criação de anomalias."""
from flask import Blueprint
from flask_login import login_required
from ..controllers import log_controller

log_bp = Blueprint("log", __name__, url_prefix="/logs-view")

# Página com tabela paginada de logs ES
log_bp.route("/", endpoint="list_logs")(login_required(log_controller.list_logs))

# Criação de anomalia via POST JSON {index, id}
log_bp.route("/create_anomaly", methods=["POST"], endpoint="create_anomaly")(
    login_required(log_controller.create_anomaly_from_log)
)
