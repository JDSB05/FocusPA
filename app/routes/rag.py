from flask import Blueprint, request, Response, stream_with_context, jsonify
from flask_login import login_required
import time


from app.extensions import mcp_client
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession as MCPClientSession
from flask_login import current_user

# import sys
# sys.path.insert(0, "../../mcp_files")
# from mcp_files.secure_mcp_client import SimpleAuthClient
# import mcp_files


# mantém o nome do módulo/func principal já usado noutros pontos
from app.controllers.rag_controller import (
    query_hybrid_rag,           # compat
    query_hybrid_rag_stream,     # nova função em stream
    query_rag_stream_w_tools, # nova função sem stream com tools Ollama
    query_rag_with_mcp_tools, # nova função sem stream com tools MCP
)

rag_bp = Blueprint("rag", __name__)


# ? ===== Versao com tools MCP ===== ? #

def _fake_role_from_user() -> str:
    if getattr(current_user, "is_authenticated", False) and getattr(current_user, "username", None) != "user":
        return "admin"
    return "user"

@rag_bp.route("/rag", methods=["POST"])
@login_required
async def rag_query():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    messages = data.get("messages") or []  # histórico vindo do browser (lista de {role, content})
    max_es_logs = data.get("max_es_logs")
    max_chroma_chunks = data.get("max_chroma_chunks")

    if not question and not (isinstance(messages, list) and len(messages) > 0):
        return jsonify({"error": "Missing 'question' or 'messages'"}), 400

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Content-Type": "text/plain; charset=utf-8",
    }

    response = None
    try:

        # !!! TODO: Substituir isto por algo mais seguro !!!
        role = _fake_role_from_user()
        # !!! TODO: Substituir isto por algo mais seguro !!!

        # ! Test scopes
        # response = await mcp_client.call_greet_tool(name="FocusPA", role=role)
        response = await mcp_client.query_rag_with_mcp_tools(question=question, messages=messages)
        print(response)


    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return Response(response, headers=headers)



# ? ===== Versao com tools do Ollama ===== ? #

# @rag_bp.route("/rag", methods=["POST"])
# @login_required
# def rag_query():
#     data = request.get_json(silent=True) or {}
#     question = (data.get("question") or "").strip()
#     messages = data.get("messages") or []  # histórico vindo do browser (lista de {role, content})
#     max_es_logs = data.get("max_es_logs")
#     max_chroma_chunks = data.get("max_chroma_chunks")

#     if not question and not (isinstance(messages, list) and len(messages) > 0):
#         return jsonify({"error": "Missing 'question' or 'messages'"}), 400

#     def generate():
#         start_time = time.time()
#         try:
#             # stream apenas do texto final (o mais simples possível)
#             for chunk in query_rag_stream_w_tools(
#                 question=question,
#                 messages=messages,
#                 max_es_logs=max_es_logs,
#                 max_chroma_chunks=max_chroma_chunks,
#             ):
#                 # enviar logo que chega
#                 yield chunk
#         except Exception as e:
#             yield f"\n\n[erro] {e}\n"
#         finally:
#             duration = time.time() - start_time
#             print(f"[INFO] [LLM] Tempo de resposta (stream): {duration:.2f} segundos")

#     headers = {
#         "Cache-Control": "no-cache",
#         "X-Accel-Buffering": "no",
#         "Content-Type": "text/plain; charset=utf-8",
#     }
#     return Response(stream_with_context(generate()), headers=headers)


# ? ===== Versao com stream normal ===== ? #

# @rag_bp.route("/rag", methods=["POST"])
# @login_required
# def rag_query():
#     data = request.get_json(silent=True) or {}
#     question = (data.get("question") or "").strip()
#     messages = data.get("messages") or []  # histórico vindo do browser (lista de {role, content})
#     max_es_logs = data.get("max_es_logs")
#     max_chroma_chunks = data.get("max_chroma_chunks")

#     if not question and not (isinstance(messages, list) and len(messages) > 0):
#         return jsonify({"error": "Missing 'question' or 'messages'"}), 400

#     def generate():
#         start_time = time.time()
#         try:
#             # stream apenas do texto final (o mais simples possível)
#             for chunk in query_hybrid_rag_stream(
#                 question=question,
#                 messages=messages,
#                 max_es_logs=max_es_logs,
#                 max_chroma_chunks=max_chroma_chunks,
#             ):
#                 # enviar logo que chega
#                 yield chunk
#         except Exception as e:
#             yield f"\n\n[erro] {e}\n"
#         finally:
#             duration = time.time() - start_time
#             print(f"[INFO] [LLM] Tempo de resposta (stream): {duration:.2f} segundos")

#     headers = {
#         "Cache-Control": "no-cache",
#         "X-Accel-Buffering": "no",
#         "Content-Type": "text/plain; charset=utf-8",
#     }
#     return Response(stream_with_context(generate()), headers=headers)