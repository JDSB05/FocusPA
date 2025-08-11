from datetime import datetime
import os
import re
import requests
from sentence_transformers import SentenceTransformer, util
from app.services.chroma_client import chroma
from app.services.elastic import es

# ===== Config =====
EMBED_MODEL = os.environ.get(
    "EMBED_MODEL",
    "PORTULAN/serafim-900m-portuguese-pt-sentence-encoder"  # melhor para PT-PT
    # alternativa mínima (multilingue): "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
LLM_URL = os.environ.get("LLM_URL", "http://localhost:11434/api/generate")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-r1")

# ===== Embeddings =====
embedder = SentenceTransformer(EMBED_MODEL)

# =====   Texto    =====
def delete_think(text: str) -> str:
    return re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)

def is_nullish_query(text: str) -> bool:
    if text is None:
        return True
    t = str(text).strip()
    # cobre "null", "NULL", ```null```, "null\n", etc.
    t = t.strip('`"\' \n\r\t').lower()
    return t == "null" or t == ""


# ===== LLM client =====
def ask_llm(prompt: str) -> str:
    try:
        resp = requests.post(
            LLM_URL,
            json={"model": LLM_MODEL, "prompt": prompt, "stream": False}
        )
        data = resp.json()
        if "response" in data:
            return delete_think(data["response"])
        if "message" in data and "content" in data["message"]:
            return delete_think(data["message"]["content"])
        raise RuntimeError(f"Resposta inesperada do LLM: {data}")
    except Exception as e:
        return f"❌ Erro ao contactar o LLM: {e}"

def reformulate_for_es(question: str) -> str:
    prompt = f"""Reformula a pergunta para pesquisa em Windows Event Logs (winlog) no Elasticsearch.
Usa campos típicos como @timestamp, event.code, winlog.event_id, user.name, access_mask, log.level, log_name.
Inclui intervalo temporal se existir na pergunta. Responde só com a query final numa linha. Hoje é {datetime.utcnow().isoformat()}Z.
Se a pergunta original for muito vaga, devolve apenas: null (sem aspas).

Pergunta:
{question}

Query reformulada:"""
    text = ask_llm(prompt).strip()
    # se vier vazio, mantém a original; se for "null", deixa passar "null"
    return text if text else question

def es_search(query_text: str, time_from: str | None = None, time_to: str | None = None, size: int = 20):
    """
    Pesquisa básica por BM25 no campo 'message' com filtro temporal opcional.
    """
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
        "_source": ["@timestamp", "event.code", "winlog.event_id", "user.name", "message", "log.file.path"],
        "size": size
    }
    try:
        res = es.search(index="winlog-*", body=body)
        hits = res.get("hits", {}).get("hits", [])
        return [h["_source"] for h in hits]
    except Exception as e:
        print(f"[WARN] [Elasticsearch] {e}")
        return []

def chroma_search(query_text: str, n_results: int = 5):
    """
    NÃO recodifica o corpus. Assume que os documentos já foram inseridos na collection com embeddings no ingest.
    """
    try:
        if not chroma.heartbeat():
            return []
        collection = chroma.get_or_create_collection("policies")
        q = collection.query(query_texts=[query_text], n_results=n_results)
        docs = (q.get("documents") or [[]])[0]
        metas = (q.get("metadatas") or [[]])[0]
        # devolve pares (doc, meta) para possível uso
        return list(zip(docs, metas))
    except Exception as e:
        print(f"[WARN] [Chroma] {e}")
        return []

def build_final_prompt(context_blocks: list[str], question: str) -> str:
    context = "\n\n---\n\n".join(context_blocks)
    return f"""Contexto (logs e políticas relevantes):
{context}

Tarefa:
Responde de forma técnica e sucinta, como perito em Windows Event Logs (segurança/auditoria).
Hoje é {datetime.utcnow().isoformat()}Z.

Pergunta original:
{question}

Resposta:"""

def query_hybrid_rag(question: str, time_from: str | None = None, time_to: str | None = None) -> str:
    refined = reformulate_for_es(question)
    print(f"[INFO] Query reformulada: {refined!r}")

    # 🚫 Se a reformulação for "null" (ou vazia), não pesquises nada
    if is_nullish_query(refined):
        print("[INFO] Pergunta demasiado vaga, não há pesquisa.")
        return "A pergunta é demasiado vaga para pesquisa. Especifica melhor (ex.: intervalo temporal, event_id, user.name)."

    # 2a) ES
    es_docs = es_search(refined, time_from=time_from, time_to=time_to, size=20)
    es_blocks = [
        f"@timestamp={d.get('@timestamp')} event.code={d.get('event.code')} winlog.event_id={d.get('winlog.event_id')} user.name={d.get('user.name')}\n{d.get('message','')}"
        for d in es_docs
    ]

    # 2b) Chroma
    chroma_pairs = chroma_search(refined, n_results=5)
    chroma_blocks = [f"[POLICY]\n{doc}" for (doc, _meta) in chroma_pairs]

    blocks = es_blocks + chroma_blocks
    if not blocks:
        return "Não encontrei contexto relevante no Elasticsearch nem no Chroma para responder."
    final_prompt = build_final_prompt(blocks[:12], question)
    return ask_llm(final_prompt)