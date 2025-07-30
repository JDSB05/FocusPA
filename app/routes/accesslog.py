from flask import Blueprint
from flask_login import login_required

from ..controllers import accesslog_controller

accesslog_bp = Blueprint('accesslog', __name__, url_prefix='/accesslogs')

accesslog_bp.route('/', endpoint='list_logs')(login_required(accesslog_controller.list_logs))
