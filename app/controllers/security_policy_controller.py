# app/controllers/security_policy_controller.py
from flask import jsonify, request, render_template
from http import HTTPStatus

from ..utils.policy import load_policy, save_policy

def policy_page():
    """GET /security_policy/page — renderiza a UI"""
    return render_template("pages/security_policy.html")

def get_policy():
    """GET /security_policy/ — devolve a policy atual (JSON)"""
    return jsonify(load_policy(force=True))

def replace_policy():
    """PUT /security_policy/ — substitui a policy inteira"""
    data = request.get_json(silent=True, force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON inválido."}), HTTPStatus.BAD_REQUEST
    try:
        saved = save_policy({
            "admins": data.get("admins", []),
            "dirs": data.get("dirs", []),
            "custom_prompt": data.get("custom_prompt", ""),
        })
        return jsonify(saved)
    except ValueError as e:
        return jsonify({"error": str(e)}), HTTPStatus.BAD_REQUEST
