# app/controllers/auth_mcp.py
from flask import Blueprint, request, redirect, session, url_for, jsonify
from flask_login import login_required, current_user

mcp_auth_bp = Blueprint("mcp", __name__, url_prefix="/mcp")


# whats needed:
# role2token = {'admin': InMemoryTokenStorage(), 'user': InMemoryTokenStorage()}


@mcp_auth_bp.route("/callback/<string:role>")
def oauth_callback(role: str):
    # print("DDEDBUGGGGGGGG")
    from app.extensions import mcp_client

    method = request.method
    query_params = request.args

    # print()
    # print parameters
    print(f"[OAUTH] Received {method} request on /callback/{role} with params:")
    for key, value in query_params.items():
        print(f"  {key}: {value}")
    print()

    if method == "GET":
        mcp_client.role_data[role]["callback_data"]["authorization_code"] = query_params["code"]
        mcp_client.role_data[role]["callback_data"]["state"] = query_params.get("state", [None])

        print(f"[OAUTH] Callback received: state={mcp_client.role_data[role]['callback_data']['state']} code=***")
        return "<h1>Authorization Successful!</h1><script>window.close()</script>"
