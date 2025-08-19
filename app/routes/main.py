from flask import Blueprint
from flask_login import login_required

from ..controllers import main_controller

main_bp = Blueprint('main', __name__)

main_bp.route('/', endpoint='dashboard')(login_required(main_controller.dashboard))
main_bp.route('/access-control', endpoint='access_control')(login_required(main_controller.access_control))
main_bp.route('/compliance', endpoint='compliance')(login_required(main_controller.compliance))
main_bp.route('/logs', methods=['POST'], endpoint='logs')(login_required(main_controller.receber_log))
main_bp.route('/search', endpoint='search')(login_required(main_controller.procurar_logs))
main_bp.route('/chat', endpoint='chat')(login_required(main_controller.chat))
