from flask import Blueprint, request, jsonify
from app.controllers.rag_controller import query_hybrid_rag

rag_bp = Blueprint("rag", __name__)

@rag_bp.route("/rag", methods=["POST"])
def rag_query():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "")
    answer = query_hybrid_rag(question)
    return jsonify({"answer": answer})
