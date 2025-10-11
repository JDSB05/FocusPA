"""
Adaptado a partir do exemplo do repo https://github.com/modelcontextprotocol/python-sdk:
    examples/snippets/servers/streamable_config.py
"""
# from app.controllers.rag_controller import es_search, _g, chroma_search

from mcp.server.fastmcp import FastMCP
import json
import os
from elasticsearch import Elasticsearch
import requests

# ? ==================================================================================================================================== ? #

def get_client() -> Elasticsearch:
    """Create an Elasticsearch client using environment vars."""
    url = os.environ.get('ELASTICSEARCH_URL', 'http://localhost:9200') # elasticsearch URL
    # health check
    req = requests.get(f"{url}/_cluster/health")
    if req.status_code != 200:
        print(f"[ERROR] Failed to connect to Elasticsearch at {url}: {req.text}")
        raise ValueError(f"Cannot connect to Elasticsearch at {url}")
    print(f"[INFO] Elasticsearch connected at {url}")
    return Elasticsearch(url)

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

def chroma_search(query, top_k=5):
    print(f"[INFO] [Chroma] Iniciando pesquisa para: {query}")
    query_embedding = embed_fn([query])[0]
    results = chroma.get_or_create_collection("policies").query(
        query_embeddings=[query_embedding], n_results=top_k
    )
    documents = results.get("documents")[0] or []
    metadatas = results.get("metadatas")[0] or results.get("metas")[0] or []
    distances = results.get("distances")[0] or []

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

def _g(d, path, default=None):
    cur = d
    for k in path.split('.'):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default

from sentence_transformers import SentenceTransformer

# Carregado uma vez, reutilizado
_model = SentenceTransformer("all-MiniLM-L6-v2")

def embed_fn(texts):
    """Recebe str ou lista[str], devolve lista[list[float]]"""
    if isinstance(texts, str):
        texts = [texts]
    return _model.encode(texts, convert_to_numpy=True).tolist()


es = get_client()

import os
import chromadb


chroma = chromadb.HttpClient(
    host=os.environ.get("CHROMA_HOST", "localhost"),
    port=int(os.environ.get("CHROMA_PORT", "8000")),
)

# ? ==================================================================================================================================== ? #


# Stateful server (maintains session state)
mcp_server = FastMCP("StatefulServer", port=9400)

# Add a simple tool to demonstrate the server (Exemplo do repo MCP)
@mcp_server.tool()
def greet(name: str = "World") -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"

@mcp_server.tool()
def es_log_search_tool(es_query: str, es_limit: int):
    """
    Log search tool from Elasticsearch.

    Args:
        es_query (str): A query in Elasticsearch DSL format.
            A valid elasticsearch query in JSON format that must follow these rules:
            - If the user question includes multiple values for a field, use 'terms' (plural) instead of 'term'.
            - Place time filters (date ranges) **always inside 'range'**, never directly as a key.
            Correct example:
            { 'range': { '@timestamp': { 'gte': '...', 'lte': '...' } } }
            - Place time filters inside 'filter' and not 'must'.
            - Must be only valid JSON
            - The JSON MUST be wrapped inside "query": { ... }

            Common fields you can use:
            - \"hour_of_day\" (range)
            - \"@timestamp\" (range)
            - \"event.code\"
            - \"winlog.event_id\"
            - \"user.name\"
            - \"access_mask\"
            - \"log.level\"
            - \"log_name\"
        es_limit (int): The maximum number of results to return.
    """

    # Tentativa de corrigir um erro comum do LLM de nao envolver a query em {"query": {...}}
    if "query" not in es_query:
        es_query = f'{{"query": {es_query}}}'

    if es_limit > 0:
        es_docs = es_search(es_query, size=es_limit)
        es_blocks = [
            f"@timestamp={d.get('@timestamp')} event.code={_g(d,'event.code')} "
            f"winlog.event_id={_g(d,'winlog.event_id')} user.name={_g(d,'user.name')}\n{d.get('message','')}"
            for d in es_docs
        ]

    return es_blocks

@mcp_server.tool()
def chroma_policy_search_tool(chroma_query: str, chroma_limit: int = 5):
    """
    Search the ChromaDB for relevant policy documents.

    Args:
        chroma_query (str): The search query.
        chroma_limit (int): The number of top results to return, having a default of 5.
    """
    chroma_blocks: list[str] = []
    if chroma_limit > 0:
        chroma_pairs = chroma_search(chroma_query, top_k=chroma_limit)
        chroma_blocks = [f"[POLICY]\n{p['text']}" for p in chroma_pairs if p.get("text")]

    return chroma_blocks


if __name__ == "__main__":
    mcp_server.run(transport="streamable-http")




# E possivel mudar a forma como as mcp tools sao apresentadas ao mcp client

# @mcp_server.list_tools()
# async def handle_list_tools() -> list[mcp.types.Tool]:
#     """List available tools."""
#     return [
#         mcp.types.Tool(
#             name="query_db",
#             description="Query the database",
#             inputSchema={
#                 "type": "object",
#                 "properties": {"query": {"type": "string", "description": "SQL query to execute"}},
#                 "required": ["query"],
#             },
#         )
#     ]