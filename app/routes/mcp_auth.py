from flask import Blueprint
# from flask_login import login_required

from ..controllers import auth_mcp_controller

mcp_auth_bp = Blueprint("mcp", __name__, url_prefix="/mcp")

mcp_auth_bp.route("/callback/<string:role>", endpoint="oauth_callback")(auth_mcp_controller.oauth_callback)
