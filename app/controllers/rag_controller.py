import os
from sentence_transformers import SentenceTransformer, util
from app.services.chroma_client import chroma
from app.services.elastic import es
import requests

# Carrega o modelo de embeddings
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# URL do LLM configurável via variável de ambiente
LLM_URL = os.environ.get("LLM_URL", "http://localhost:11434/api/generate")

def ask_llm(prompt: str) -> str:
    """Envia o prompt ao LLM e retorna a resposta gerada."""
    print(f"[INFO] [LLM] Enviando prompt ao LLM: {prompt[:100]}...")  # Log do início do prompt
    try:
        resp = requests.post(
            LLM_URL,
            json={"model": "mistral", "prompt": prompt, "stream": False}
        )
        data = resp.json()
        if "response" in data:
            return data["response"]
        if "message" in data and "content" in data["message"]:
            return data["message"]["content"]
        print(f"[ERROR] [LLM] Resposta inesperada do LLM: {data}")
        raise RuntimeError(f"Resposta inesperada do LLM: {data}")
    except Exception as e:
        return f"❌ Erro ao contactar o LLM: {e}"

def query_hybrid_rag(question: str) -> str:
    """Combina pesquisa full-text (ES) e vetorial (Chroma) antes de interrogar o LLM."""

    # 1️⃣ Pesquisa full-text no Elasticsearch (logs do Windows)
    es_docs = []
    try:
        result = es.search(
            index="winlog-*",
            size=3,
            query={"match": {"message": question}},
            _source=["message"] # type: ignore
        )
        es_docs = [hit["_source"]["message"] for hit in result["hits"]["hits"]]
        print(f"[INFO] [Elasticsearch] Encontrados {len(es_docs)} documentos relevantes.")
    except Exception as e:
        print(f"[WARN] [Elasticsearch] Erro ao consultar Elasticsearch: {e}")

    # 2️⃣ Pesquisa vetorial em ChromaDB (políticas)
    chroma_docs = []
    try:
        if chroma.heartbeat():
            collection = chroma.get_or_create_collection("policies")
            print(f"[INFO] [Chroma] Collection 'policies' encontrada: {collection.name}")
            all_docs = collection.get()["documents"] or []
            print(f"[INFO] [Chroma] Documentos encontrados na coleção 'policies': {len(all_docs)}") 
            if all_docs:
                q_emb = embedder.encode(question, convert_to_tensor=True)
                corpus_emb = embedder.encode(all_docs, convert_to_tensor=True)
                hits = util.semantic_search(q_emb, corpus_emb, top_k=3)[0]
                chroma_docs = [all_docs[int(h['corpus_id'])] for h in hits]
    except Exception as e:
        print(f"[WARN] [Chroma] Erro ao consultar Chroma: {e}")

    # 3️⃣ Monta o prompt
    context = "\n\n".join(es_docs + chroma_docs)
    if not context:
        print("[WARN] [Chroma] Nenhum documento de contexto encontrado.")

    prompt = f"Contexto:\n{context}\n\nPergunta: {question}\nResposta:"
    return ask_llm(prompt)