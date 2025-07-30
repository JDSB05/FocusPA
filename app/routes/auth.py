from flask import Blueprint
from flask_login import login_required

from ..controllers import auth_controller

auth_bp = Blueprint('auth', __name__)

auth_bp.route('/login', methods=['GET', 'POST'], endpoint='login')(auth_controller.login)
auth_bp.route('/register', methods=['GET', 'POST'], endpoint='register')(auth_controller.register)
auth_bp.route('/logout', endpoint='logout')(login_required(auth_controller.logout))
