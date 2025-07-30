# app/routes/rag.py
from flask import Blueprint, request, jsonify
from app.controllers.rag_controller import query_policies_with_rag

rag_bp = Blueprint("rag", __name__)

@rag_bp.route("/rag", methods=["POST"])
def rag_query():
    data = request.json
    question = data.get("question", "") if data else ""
    answer = query_policies_with_rag(question)
    return jsonify({"answer": answer})
