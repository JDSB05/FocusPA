from datetime import datetime
import os
import re
import json
import requests

from sentence_transformers import util
from sentence_transformers import SentenceTransformer

from app.services.embeddings import embed as embed_fn
from app.services.chroma_client import chroma
from app.services.elastic import es

# ===== Config =====
EMBED_MODEL = os.environ.get(
    "EMBED_MODEL",
    "PORTULAN/serafim-900m-portuguese-pt-sentence-encoder"
    # alternativa mínima (multilingue): "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
LLM_URL = os.environ.get("LLM_URL", "http://localhost:11434/api/generate")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-r1")

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

# ===== LLM (não-stream, compat) =====
def ask_llm(prompt: str, model: str) -> str:
    try:
        resp = requests.post(
            LLM_URL,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=None,
        )
        data = resp.json()
        if "response" in data:
            return delete_think(data["response"])
        if "message" in data and "content" in data["message"]:
            return delete_think(data["message"]["content"])
        raise RuntimeError(f"Resposta inesperada do LLM: {data}")
    except Exception as e:
        return f"❌ Erro ao contactar o LLM: {e}"

# ===== LLM (stream) =====
def ask_llm_stream(prompt: str):
    """
    Gera chunks de texto à medida que chegam do LLM. Mantém o <think> se o modelo o emitir.
    Compatível com Ollama /api/generate (JSON por linha com 'response' e 'done').
    """
    try:
        with requests.post(
            LLM_URL,
            json={"model": LLM_MODEL, "prompt": prompt, "stream": True},
            stream=True,
            timeout=None,
        ) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines():
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                line = raw.strip()

                try:
                    obj = json.loads(line)
                    if "response" in obj:
                        yield obj["response"]
                    elif "message" in obj and isinstance(obj["message"], dict) and "content" in obj["message"]:
                        yield obj["message"]["content"]
                    if obj.get("done") is True:
                        break
                except Exception:
                    # fallback: texto cru
                    yield line
    except Exception as e:
        yield f"\n❌ Erro ao contactar o LLM: {e}\n"

# ===== Reformulação =====
def reformulate_for_es(question: str) -> str:
    prompt = f"""
Reformula a pergunta para uma query Elasticsearch em JSON válido, SEM comentários ou texto fora do JSON.
Regras:
- Se a pergunta incluir vários valores para um campo, usar "terms" (plural) em vez de "term".
- Colocar filtros temporais (intervalos de datas) dentro de "filter" e não "must".
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
    text = ask_llm(prompt, "deepseek-coder-v2").strip()
    text = strip_json_markdown(text)
    return text if text else question

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
    except json.JSONDecodeError:
        print("[INFO] Query ES não é JSON. A usar BM25.")
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
        return [h["_source"] for h in hits]
    except Exception as e:
        print(f"[WARN] [Elasticsearch] {e}")
        return []

# ===== Chroma =====
def chroma_search(query_text: str, n_results: int = 5):
    try:
        if not chroma.heartbeat():
            print("[WARN] [Chroma] ChromaDB não está disponível.")
            return []
        collection = chroma.get_or_create_collection("policies")
        q_emb = embed_fn(query_text)
        res = collection.query(
            query_embeddings=q_emb,
            n_results=n_results,
            where=None,
            include=["documents", "metadatas"]
        )
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        return list(zip(docs, metas))
    except Exception as e:
        print(f"[WARN] [Chroma] {e}")
        return []

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
        f"@timestamp={d.get('@timestamp')} event.code={d.get('event.code')} winlog.event_id={d.get('winlog.event_id')} user.name={d.get('user.name')}\n{d.get('message','')}"
        for d in es_docs
    ]
    chroma_pairs = chroma_search(refined, n_results=5)
    chroma_blocks = [f"[POLICY]\n{doc}" for (doc, _meta) in chroma_pairs]

    blocks = es_blocks + chroma_blocks
    if not blocks:
        return "Não encontrei contexto relevante no Elasticsearch nem no Chroma para responder."
    final_prompt = build_final_prompt(blocks[:12], question)
    return ask_llm(final_prompt, LLM_MODEL)

# ===== RAG (stream) =====
def query_hybrid_rag_stream(question: str, time_from: str | None = None, time_to: str | None = None):
    refined = reformulate_for_es(question)
    print(f"[INFO] Query reformulada (stream): {refined!r}")

    if is_nullish_query(refined):
        yield "A pergunta é demasiado vaga para pesquisa. Especifica melhor (ex.: intervalo temporal, event_id, user.name)."
        return

    es_docs = es_search(refined, time_from=time_from, time_to=time_to, size=20)
    es_blocks = [
        f"@timestamp={d.get('@timestamp')} event.code={d.get('event.code')} winlog.event_id={d.get('winlog.event_id')} user.name={d.get('user.name')}\n{d.get('message','')}"
        for d in es_docs
    ]
    chroma_pairs = chroma_search(refined, n_results=5)
    chroma_blocks = [f"[POLICY]\n{doc}" for (doc, _meta) in chroma_pairs]

    blocks = es_blocks + chroma_blocks
    if not blocks:
        yield "Não encontrei contexto relevante no Elasticsearch nem no Chroma para responder."
        return

    final_prompt = build_final_prompt(blocks[:12], question)

    # aplica o filtro no streaming
    for piece in delete_think_stream(ask_llm_stream(final_prompt)):
        yield piece