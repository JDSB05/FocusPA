# /controllers/rag_controller.py
from datetime import datetime
import os
import re
import json
import requests
from ollama import Client

from sentence_transformers import util
from sentence_transformers import SentenceTransformer

from app.services.embeddings import embed as embed_fn
from app.services.chroma_client import chroma
from app.services.elastic import es
from dotenv import load_dotenv

# ===== Config =====

load_dotenv(dotenv_path='../.env')

EMBED_MODEL = os.environ.get(
    "EMBED_MODEL",
    "PORTULAN/serafim-900m-portuguese-pt-sentence-encoder"
    # alternativa mínima (multilingue): "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
LLM_URL = os.environ.get("LLM_URL", "http://localhost:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-r1")
LLM_MODEL_LIGHT = os.environ.get("LLM_MODEL_LIGHT", "deepseek-coder-v2")

ollama = Client(
  host=LLM_URL,
  headers={'x-some-header': 'some-value'}
)

# ===== Embeddings =====
embedder = SentenceTransformer(EMBED_MODEL)

# ===== Util =====
def delete_think(text: str) -> str:
    return re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)

def delete_think_stream(chunks):
    """
    Recebe um iterável/gerador de chunks e devolve-os removendo <think>...</think>.
    Suporta tags partidas entre chunks.
    """
    inside_think = False
    buffer = ""

    for chunk in chunks:
        if not chunk:
            continue

        i = 0
        while i < len(chunk):
            if not inside_think:
                start_tag = chunk.find("<think>", i)
                if start_tag == -1:
                    buffer += chunk[i:]
                    break
                else:
                    buffer += chunk[i:start_tag]
                    inside_think = True
                    i = start_tag + len("<think>")
            else:
                end_tag = chunk.find("</think>", i)
                if end_tag == -1:
                    # ainda dentro de <think>, descarta até vir o fecho
                    break
                else:
                    inside_think = False
                    i = end_tag + len("</think>")

        if buffer:
            yield buffer
            buffer = ""

    # flush final se sobrou texto
    if buffer:
        yield buffer


def is_nullish_query(text: str) -> bool:
    if text is None:
        return True
    t = str(text).strip()
    t = t.strip('`"\' \n\r\t').lower()
    return t == "null" or t == ""

def strip_json_markdown(text: str) -> str:
    """
    Remove blocos de código markdown como ```json ... ``` ou ``` ... ```.
    Retorna apenas o conteúdo JSON puro.
    """
    if not text:
        return text

    # remover ```json ... ```
    if text.strip().startswith("```"):
        lines = text.strip().splitlines()
        # remove primeira e última linha se forem fences ```
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    return text.strip()

def build_es_query_from_events(events_json):
    if isinstance(events_json, str):
        try:
            events = json.loads(events_json)
        except Exception:
            events = [events_json]
    elif isinstance(events_json, dict):
        events = [events_json]
    else:
        events = events_json or []

    should = []
    for event in events:
        if isinstance(event, dict):
            txt = event.get("event") or event.get("message") or event.get("description") or ""
        else:
            txt = str(event)
        if txt:
            should.append({"match": {"message": {"query": txt}}})

    return {"query": {"bool": {"should": should}}} if should else {"query": {"match_none": {}}}

def _g(d, path, default=None):
    cur = d
    for k in path.split('.'):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default

# ===== LLM (não-stream, compat) =====

def ask_llm(prompt: str, model: str) -> str:
    try:
        print(f"[ask_llm] Enviando prompt para modelo '{model}'...")
        prompt = prompt.lstrip("\u0001")

        # Chamada ao Ollama (lib Python)
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extrair a resposta do LLM
        if "message" in response and "content" in response["message"]:
            answer = response["message"]["content"]
        elif "response" in response:
            answer = response["response"]
        else:
            raise RuntimeError(f"Resposta inesperada do LLM: {response}")

        print(f"[ask_llm] Resposta recebida do LLM: {answer[:80]}...")
        return delete_think(answer)

    except Exception as e:
        return f"❌ Erro ao contactar o LLM: {e}"

# ===== LLM (stream) =====
def ask_llm_stream(
    prompt: str | None = None,
    model: str = LLM_MODEL,
    messages: list[dict] | None = None
):
    """
    Stream de resposta do LLM via biblioteca ollama.
    Se `messages` vier do browser, envia-as tal como estão (formato chat):
      [{"role":"system"|"user"|"assistant", "content":"..."}]
    Caso contrário, usa um único prompt como mensagem de utilizador.
    """
    try:
        # Normaliza mensagens vindas do browser (se existirem)
        if messages and isinstance(messages, list):
            msgs = []
            for m in messages:
                role = (m.get("role") or "user").lower()
                content = (m.get("content") or "").lstrip("\u0001")
                if content:
                    msgs.append({"role": role, "content": content})
            # se só vieram mensagens do assistente, garante última do user
            if (not msgs or msgs[-1]["role"] not in ("user", "system")) and prompt:
                msgs.append({"role": "user", "content": prompt.lstrip("\u0001")})
            if not msgs:
                raise ValueError("ask_llm_stream: histórico vazio.")
        else:
            # fallback: single-turn com prompt
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError("ask_llm_stream: precisa de `prompt` ou `messages`.")
            msgs = [{"role": "user", "content": prompt.lstrip("\u0001")}]

        # Streaming com Ollama
        stream = ollama.chat(
            model=model,
            messages=msgs,
            stream=True,
            think=False
        )

        for chunk in stream:
            # Cada chunk pode vir como {"message": {"content": "..."}}
            # ou (alguns modelos) {"response": "..."}
            content = (chunk.get("message") or {}).get("content") or chunk.get("response")
            if content:
                yield content
            if chunk.get("done"):
                break

    except Exception as e:
        print(f"[ERROR] ask_llm_stream: {e}")   
        yield f"\n❌ Erro ao contactar o LLM: {e}\n"

# ===== Reformulação =====
def reformulate_for_es(question: str) -> str:
    prompt = f"""
Reformula a pergunta para uma query Elasticsearch em JSON válido, SEM comentários ou texto fora do JSON.
Regras:
- Se a pergunta incluir vários valores para um campo, usar "terms" (plural) em vez de "term".
- Colocar filtros temporais (intervalos de datas) **sempre dentro de "range"**, nunca diretamente como chave.
  Exemplo correto:
  {{ "range": {{ "@timestamp": {{ "gte": "...", "lte": "..." }} }} }}
- Colocar filtros temporais dentro de "filter" e não "must".
- Devolver apenas JSON válido, nada mais.
- Se a pergunta for muito vaga e não houver dados suficientes para gerar a query, devolver apenas: null

Campos comuns que podes usar: 
- "@timestamp" (range)
- "event.code"
- "winlog.event_id"
- "user.name"
- "access_mask"
- "log.level"
- "log_name"

Hoje é {datetime.utcnow().isoformat()}Z.

Pergunta original:
{question}

Resposta (apenas JSON ou null):
"""
    try:
        text = ask_llm(prompt, LLM_MODEL_LIGHT).strip()
        text = strip_json_markdown(text)

        if text.lower() == "null":
            return "null"

        try:
            parsed = json.loads(text)
        except Exception:
            print(f"[WARN] [Reformulação] Resposta não era JSON: {text}...")
            return "null"

        if isinstance(parsed, list):
            return json.dumps(build_es_query_from_events(parsed))

        if isinstance(parsed, dict):
            return json.dumps(parsed)  # respeitar query já válida

        print(f"[WARN] [Reformulação] Tipo inesperado: {type(parsed)}")
        return "null"

    except Exception as e:
        print(f"[ERROR] [Reformulação] {e}")
        return "null"


# ===== Elasticsearch =====

def es_search(query_text: str, time_from: str | None = None, time_to: str | None = None, size: int = 20):
    """
    Se query_text for JSON válido, envia diretamente para ES.
    Caso contrário, faz pesquisa BM25 no campo 'message' com filtro temporal opcional.
    """
    try:
        # tentar interpretar como JSON
        body = json.loads(query_text)
        print("[INFO] Query ES recebida em formato JSON válido.")
        print(body)
    except json.JSONDecodeError:
        print("[INFO] Query ES não é JSON. A usar BM25.")
        print(f"[INFO] Query ES original: {query_text}")
        must = [{"match": {"message": {"query": query_text}}}]
        filter_terms = []
        if time_from or time_to:
            rng = {}
            if time_from: rng["gte"] = time_from
            if time_to:   rng["lte"] = time_to
            filter_terms.append({"range": {"@timestamp": rng}})
        body = {
            "query": {
                "bool": {
                    "must": must,
                    "filter": filter_terms
                }
            },
            "_source": [
                "@timestamp", "event.code", "winlog.event_id",
                "user.name", "message", "log.file.path"
            ],
            "size": size
        }

    try:
        res = es.search(index="winlog-*", body=body)
        hits = res.get("hits", {}).get("hits", [])
        print(f"[INFO] [Elasticsearch] Encontrados {len(hits)} resultados.")
        return [
            {**h["_source"], "_id": h["_id"], "_index": h["_index"]}
            for h in hits
        ]
    except Exception as e:
        print(f"[WARN] [Elasticsearch] {e}")
        return []

# ===== Chroma =====
def chroma_search(query, top_k=5):
    print(f"[INFO] [Chroma] Iniciando pesquisa para: {query}")
    query_embedding = embed_fn([query])[0]
    results = chroma.get_or_create_collection("policies").query(
        query_embeddings=[query_embedding], n_results=top_k
    )
    documents = results.get("documents") or []
    metadatas = results.get("metadatas") or results.get("metas") or []
    distances = results.get("distances") or []

    pairs = []
    def pick(lst, i):
        try:
            v = lst[i]
            return v[0] if isinstance(v, list) else v
        except Exception:
            return None

    for i in range(max(len(documents), len(metadatas), len(distances))):
        pairs.append({
            "text": pick(documents, i) or "",
            "meta": pick(metadatas, i) or {},
            "score": pick(distances, i) or 0.0
        })
    return pairs



# ===== Prompt =====
def build_final_prompt(context_blocks: list[str], question: str) -> str:
    context = "\n\n---\n\n".join(context_blocks)
    return f"""Contexto (logs e políticas relevantes, tens de responder baseando-te nas políticas fornecidas, as políticas estão depois dos logs):
{context}

Tarefa:
Responde de forma técnica e sucinta, como perito em Windows Event Logs (segurança/auditoria).
Hoje é {datetime.utcnow().isoformat()}Z.

Pergunta original:
{question}

Resposta:"""

# ===== RAG (compat: não stream) =====
def query_hybrid_rag(question: str, time_from: str | None = None, time_to: str | None = None) -> str:
    refined = reformulate_for_es(question)
    print(f"[INFO] Query reformulada: {refined!r}")
    if is_nullish_query(refined):
        print("[INFO] Pergunta demasiado vaga, não há pesquisa.")
        return "A pergunta é demasiado vaga para pesquisa. Especifica melhor (ex.: intervalo temporal, event_id, user.name)."

    es_docs = es_search(refined, time_from=time_from, time_to=time_to, size=20)
    es_blocks = [
        f"@timestamp={d.get('@timestamp')} event.code={_g(d,'event.code')} "
        f"winlog.event_id={_g(d,'winlog.event_id')} user.name={_g(d,'user.name')}\n{d.get('message','')}"
        for d in es_docs
    ]
    chroma_pairs = chroma_search(question, top_k=5)  # usar pergunta natural
    chroma_blocks = [f"[POLICY]\n{p['text']}" for p in chroma_pairs if p.get("text")]

    blocks = es_blocks + chroma_blocks
    if not blocks:
        return "Não encontrei contexto relevante no Elasticsearch nem no Chroma para responder."
    final_prompt = build_final_prompt(blocks[:12], question)
    return ask_llm(final_prompt, LLM_MODEL)

# ----- RAG (stream)
def query_hybrid_rag_stream(
    question: str,
    time_from: str | None = None,
    time_to: str | None = None,
    messages: list[dict] | None = None,   # histórico do browser
    model: str = LLM_MODEL,                # usa o teu default
):
    """
    Constrói contexto via RAG (ES + Chroma), injeta como mensagem SYSTEM
    e envia para o LLM juntamente com o histórico do browser (messages).
    """
    # Pergunta efetiva a usar no RAG (se question vier vazio, tenta última do user)
    def _last_user_question(msgs):
        if not isinstance(msgs, list):
            return ""
        for m in reversed(msgs):
            if (m.get("role") or "").lower() == "user":
                txt = (m.get("content") or "").strip()
                if txt:
                    return txt
        return ""

    final_question = (question or "").strip() or _last_user_question(messages)
    if not final_question:
        yield "Pergunta vazia."
        return

    refined = reformulate_for_es(final_question)
    print(f"[INFO] Query reformulada (stream): {refined!r}")

    if is_nullish_query(refined):
        yield "A pergunta é demasiado vaga para pesquisa. Especifica melhor (ex.: intervalo temporal, event_id, user.name)."
        return

    # ---- Elasticsearch ----
    es_docs = es_search(refined, time_from=time_from, time_to=time_to, size=20)
    es_blocks = [
        f"@timestamp={d.get('@timestamp')} event.code={_g(d,'event.code')} "
        f"winlog.event_id={_g(d,'winlog.event_id')} user.name={_g(d,'user.name')}\n{d.get('message','')}"
        for d in es_docs
    ]

    # ---- Chroma (políticas) ----
    chroma_pairs = chroma_search(final_question, top_k=5)  # usa pergunta natural
    chroma_blocks = [f"[POLICY]\n{p['text']}" for p in chroma_pairs if p.get("text")]

    blocks = es_blocks + chroma_blocks
    if not blocks:
        yield "Não encontrei contexto relevante no Elasticsearch nem no Chroma para responder."
        return

    # ---- Mensagem SYSTEM com o contexto RAG ----
    context = "\n\n---\n\n".join(blocks[:12])
    system_ctx = (
        "Contexto (logs e políticas relevantes):\n"
        f"{context}\n\n"
        "Instruções:\n"
        "- Responde de forma técnica e sucinta, como perito em Windows Event Logs (segurança/auditoria).\n"
        "- Usa apenas o contexto acima. Se faltar informação, diz explicitamente o que falta.\n"
        f"- Hoje é {datetime.utcnow().isoformat()}Z.\n"
    )

    # ---- Normaliza histórico do browser (mantém últimas N mensagens) ----
    N = 12
    norm_msgs = []
    if isinstance(messages, list):
        for m in messages[-N:]:
            role = (m.get("role") or "user").lower()
            content = (m.get("content") or "").lstrip("\u0001")
            if content:
                norm_msgs.append({"role": role, "content": content})

    # Garante que a última mensagem do histórico é a 'final_question' (do user)
    if not norm_msgs or norm_msgs[-1]["role"] != "user":
        norm_msgs.append({"role": "user", "content": final_question})

    # ---- Compose mensagens para o LLM (SYSTEM + histórico do browser) ----
    combined_messages = [{"role": "system", "content": system_ctx}] + norm_msgs

    # ---- Chamada ao LLM em stream (com limpeza do <think> se aplicares) ----
    try:
        for piece in delete_think_stream(
            ask_llm_stream(
                prompt=None,  # usamos messages
                model=model,
                messages=combined_messages
            )
        ):
            yield piece
    except Exception as e:
        yield f"\n❌ Erro ao contactar o LLM: {e}\n"