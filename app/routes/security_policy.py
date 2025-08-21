# app/routes/security_policy.py
from flask import Blueprint
from flask_login import login_required

from ..controllers import security_policy_controller

security_policy_bp = Blueprint('security_policy', __name__, url_prefix='/security_policy')

# Página HTML
security_policy_bp.route('/page', methods=['GET'], endpoint='policy_page')(
    login_required(security_policy_controller.policy_page)
)

# API JSON
security_policy_bp.route('/', methods=['GET'], endpoint='get_policy')(
    login_required(security_policy_controller.get_policy)
)
security_policy_bp.route('/', methods=['PUT'], endpoint='replace_policy')(
    login_required(security_policy_controller.replace_policy)
)
