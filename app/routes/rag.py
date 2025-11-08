from flask import Blueprint, request, Response, stream_with_context, jsonify
from flask_login import login_required
import time


from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession as MCPClientSession


# mantém o nome do módulo/func principal já usado noutros pontos
from app.controllers.rag_controller import (
    query_hybrid_rag,           # compat
    query_hybrid_rag_stream,     # nova função em stream
    query_rag_stream_w_tools, # nova função sem stream com tools Ollama
    query_rag_with_mcp_tools, # nova função sem stream com tools MCP
)

rag_bp = Blueprint("rag", __name__)


# ? ===== Versao com tools MCP ===== ? #

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

   
    async def generate(mcp_session: MCPClientSession | None = None):

        start_time = time.time()
        try:
            response = await query_rag_with_mcp_tools(
                question=question,
                messages=messages,
                max_es_logs=max_es_logs,
                max_chroma_chunks=max_chroma_chunks,
                mcp_session=mcp_session,
            )

        except Exception as e:
            return f"\n\n[erro] {e}\n"
        finally:
            duration = time.time() - start_time
            print(f"[INFO] [LLM] Tempo de resposta (stream): {duration:.2f} segundos")

        return response

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Content-Type": "text/plain; charset=utf-8",
    }

    try:
        async with streamablehttp_client("http://localhost:9400/mcp") as (read_stream, write_stream, _):
            async with MCPClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await generate(mcp_session=session)

    except Exception as e:
        print(f"\033[93m[ERROR] [MCP SERVER] MCP session initialization failed: {e}\033[0m")
        response = await generate(mcp_session=None)

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