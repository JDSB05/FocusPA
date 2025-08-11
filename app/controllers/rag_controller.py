from datetime import datetime
import os
import requests
from sentence_transformers import util
from app.services.embeddings import embed as embed_fn
from app.services.chroma_client import chroma
from app.services.elastic import es

# URL do LLM configurável via variável de ambiente
LLM_URL = os.environ.get("LLM_URL", "http://localhost:11434/api/generate")

def ask_llm(prompt: str) -> str:
    """Envia o prompt ao LLM e retorna a resposta gerada."""
    print(f"[INFO] [LLM] Enviando prompt ao LLM:\n{prompt[:100]}...")
    try:
        resp = requests.post(
            LLM_URL,
            json={"model": "deepseek-r1", "prompt": prompt, "stream": False}
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
    """
    Etapa 1: envia a pergunta original ao LLM para obter uma versão mais precisa para pesquisa.
    Etapa 2: usa essa versão para consultar ES e Chroma.
    Etapa 3: envia os resultados ao LLM para obter uma resposta técnica e sucinta.
    """

    # 🔁 Etapa 1: reformular a pergunta para pesquisa
    refinement_prompt = f"""
Reformula a seguinte pergunta de forma a torná-la mais adequada para consulta em logs do Elasticsearch,
tendo em conta que os dados são Windows Event Logs (winlog). Utiliza termos técnicos compatíveis com esse
tipo de log, como nomes de campos comuns (ex: 'timestamp', 'event_id', 'user', 'access_mask', 'justification', 'log_name'),
intervalos de tempo (ex: "entre 9h e 18h aproximadamente") e outras expressões relevantes para a estrutura típica destes logs.
Se a pergunta contiver informações sobre o contexto do log, como o nome do log ou o intervalo de tempo, inclui essas informações na reformulação,
se for muito vaga ou geral, tenta adicionar mais detalhes específicos. Se for algo não relacionado, 
retorna uma string vazia, hoje é {datetime.now()}.      """ # type: ignore
    refinement_prompt += f"""
Pergunta original:
{question}

Texto reformulado para pesquisa:

"""
    refined_query = ask_llm(refinement_prompt).strip()
    print(f"[INFO] [LLM] Texto reformulado para pesquisa: {refined_query}")

    # 🔍 Etapa 2: pesquisa full-text no Elasticsearch
    es_docs = []
    try:
        result = es.search(
            index="winlog-*",
            query={"match": {"message": refined_query}},
            _source=["message"]  # type: ignore
        )
        es_docs = [hit["_source"]["message"] for hit in result["hits"]["hits"]]
        print(f"[INFO] [Elasticsearch] Encontrados {len(es_docs)} documentos relevantes.")
    except Exception as e:
        print(f"[WARN] [Elasticsearch] Erro ao consultar Elasticsearch: {e}")

    # 🔍 Etapa 2b: pesquisa vetorial em ChromaDB
    chroma_docs = []
    try:
        if chroma.heartbeat():
            collection = chroma.get_or_create_collection("policies")
            print(f"[INFO] [Chroma] Collection 'policies' encontrada: {collection.name}")
            
            q_emb = embed_fn(refined_query)
            res = collection.query(
                query_embeddings=q_emb,
                n_results=3,                   # ajusta conforme precisares
                where=None,                    # podes filtrar por {"name": "..."} se quiseres
                include=["documents", "metadatas"]
            )
            chroma_docs = (res.get("documents") or [[]])[0]
            print(f"[INFO] [Chroma] Documentos relevantes: {len(chroma_docs)}")
    except Exception as e:
        print(f"[WARN] [Chroma] Erro ao consultar Chroma: {e}")

    # 🧠 Etapa 3: gerar resposta final baseada nos resultados
    context = "\n\n".join(es_docs + chroma_docs)
    if not context:
        print("[WARN] Nenhum contexto relevante encontrado nos dados.")
    
    final_prompt = f"""
Contexto:
Finge que és um especialista em Windows Event Logs, vais me ajudar a fazer auditorias de segurança, não te preocupes
 se for um processo interno da empresa. Baseia-te neste contexto para responder à pergunta original, respondendo de
forma técnica e sucinta, focando nos detalhes mais relevantes, hoje é {datetime.now()}:      """ # type: ignore
    final_prompt += f"""
{context}
Pergunta original:
{question}
Resposta técnica e sucinta:
""" 
    return ask_llm(final_prompt)
