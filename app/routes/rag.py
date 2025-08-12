from flask import Blueprint, request, jsonify
from app.controllers.rag_controller import query_hybrid_rag
from flask_login import login_required
import time

rag_bp = Blueprint("rag", __name__)

@rag_bp.route("/rag", methods=["POST"])
@login_required
def rag_query():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "")
    if not question:
        return jsonify({"error": "Missing ‘question’ field"}), 400
    try:
        start_time = time.time()
        answer = query_hybrid_rag(question)
        duration = time.time() - start_time
        print(f"[INFO] [LLM] Tempo de resposta: {duration:.2f} segundos")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"answer": answer})
