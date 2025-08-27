from flask import Blueprint, request, Response, stream_with_context, jsonify
from flask_login import login_required
import time

# mantém o nome do módulo/func principal já usado noutros pontos
from app.controllers.rag_controller import (
    query_hybrid_rag,           # compat
    query_hybrid_rag_stream     # nova função em stream
)

rag_bp = Blueprint("rag", __name__)

@rag_bp.route("/rag", methods=["POST"])
@login_required
def rag_query():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    messages = data.get("messages") or []  # histórico vindo do browser (lista de {role, content})

    if not question and not (isinstance(messages, list) and len(messages) > 0):
        return jsonify({"error": "Missing 'question' or 'messages'"}), 400

    def generate():
        start_time = time.time()
        try:
            # stream apenas do texto final (o mais simples possível)
            for chunk in query_hybrid_rag_stream(question=question, messages=messages):
                # enviar logo que chega
                yield chunk
        except Exception as e:
            yield f"\n\n[erro] {e}\n"
        finally:
            duration = time.time() - start_time
            print(f"[INFO] [LLM] Tempo de resposta (stream): {duration:.2f} segundos")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Content-Type": "text/plain; charset=utf-8",
    }
    return Response(stream_with_context(generate()), headers=headers)