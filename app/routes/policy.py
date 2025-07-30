from flask import Blueprint
from flask_login import login_required

from ..controllers import policy_controller

policy_bp = Blueprint('policy', __name__, url_prefix='/policies')

policy_bp.route('/', endpoint='list_policies')(login_required(policy_controller.list_policies))
policy_bp.route('/new', methods=['GET', 'POST'], endpoint='new')(login_required(policy_controller.policy_new))
policy_bp.route('/<int:policy_id>/edit', methods=['GET', 'POST'], endpoint='edit')(login_required(policy_controller.policy_edit))
policy_bp.route('/<int:policy_id>/delete', methods=['POST'], endpoint='delete')(login_required(policy_controller.policy_delete))
policy_bp.route('/upload', methods=['POST'], endpoint='upload')(login_required(policy_controller.upload_policy))
