# app/controllers/rag_controller.py
import requests
from app.model import Policy
from sentence_transformers import SentenceTransformer, util

embedder = SentenceTransformer('all-MiniLM-L6-v2')

def ask_llm(prompt: str) -> str:
    """Envia prompt ao DeepSeek/Ollama."""
    response = requests.post(
        "http://localhost:11434/api/generate",  # ou /api/chat se for esse o endpoint que usas
        json={
            "model": "mistral",
            "prompt": prompt,
            "stream": False
        }
    )
    
    data = response.json()
    print("🧾 Resposta do LLM:", data)  # Debug

    # Lida com diferentes formatos possíveis
    if "response" in data:
        return data["response"]
    elif "message" in data and "content" in data["message"]:
        return data["message"]["content"]
    else:
        return "⚠️ Resposta inesperada do LLM: " + str(data)


def query_policies_with_rag(question: str) -> str:
    """Busca políticas relevantes e pergunta ao LLM."""
    all_policies = Policy.query.all()
    corpus = [p.content for p in all_policies]
    if not corpus:
        return "Não há políticas para consultar."

    question_embedding = embedder.encode(question, convert_to_tensor=True)
    corpus_embeddings = embedder.encode(corpus, convert_to_tensor=True)

    hits = util.semantic_search(question_embedding, corpus_embeddings, top_k=3)[0]
    top_docs = [corpus[int(hit['corpus_id'])] for hit in hits]

    prompt = "Contexto:\n" + "\n\n".join(top_docs) + f"\n\nPergunta: {question}\nResposta:"
    return ask_llm(prompt)
