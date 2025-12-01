"""
MCP Resource Server with Token Introspection.

This server validates tokens via Authorization Server introspection and serves MCP resources.
Demonstrates RFC 9728 Protected Resource Metadata for AS/RS separation.
"""

import datetime
import logging
from typing import Any, Literal

import click
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp.server import FastMCP

from token_verifier import IntrospectionTokenVerifier
from mcp.server.fastmcp.server import Context

logger = logging.getLogger(__name__)


# ? ==================================================================================================================================== ? #

from elasticsearch import Elasticsearch
import requests
import os
import chromadb



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
import traceback


chroma = chromadb.HttpClient(
    host=os.environ.get("CHROMA_HOST", "localhost"),
    port=int(os.environ.get("CHROMA_PORT", "8000")),
)

# ? ==================================================================================================================================== ? #




import json

class ResourceServerSettings(BaseSettings):
    """Settings for the MCP Resource Server."""

    model_config = SettingsConfigDict(env_prefix="MCP_RESOURCE_")

    # Server settings
    host: str = "localhost"
    port: int = 8002
    server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8002")

    # Authorization Server settings
    auth_server_url: AnyHttpUrl = AnyHttpUrl("http://localhost:9001")
    auth_server_introspection_endpoint: str = "http://localhost:9001/introspect"
    # No user endpoint needed - we get user data from token introspection

    # MCP settings
    mcp_scope: str = "user"

    # RFC 8707 resource validation
    oauth_strict: bool = False

    # TODO(Marcelo): Is this even needed? I didn't have time to check.
    def __init__(self, **data: Any):
        """Initialize settings with values from environment variables."""
        super().__init__(**data)


def create_resource_server(settings: ResourceServerSettings) -> FastMCP:
    """
    Create MCP Resource Server with token introspection.

    This server:
    1. Provides protected resource metadata (RFC 9728)
    2. Validates tokens via Authorization Server introspection
    3. Serves MCP tools and resources
    """
    # Create token verifier for introspection with RFC 8707 resource validation
    token_verifier = IntrospectionTokenVerifier(
        introspection_endpoint=settings.auth_server_introspection_endpoint,
        server_url=str(settings.server_url),
        validate_resource=settings.oauth_strict,  # Only validate when --oauth-strict is set
    )

    # Create FastMCP server as a Resource Server
    app = FastMCP(
        name="MCP Resource Server",
        instructions="Resource Server that validates tokens via Authorization Server introspection",
        host=settings.host,
        port=settings.port,
        debug=True,
        # Auth configuration for RS mode
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=settings.auth_server_url,
            required_scopes=[settings.mcp_scope],
            resource_server_url=settings.server_url,
        ),
    )

    @app.tool()
    def greet(name: str = "World", context: Context | None = None) -> str:
        """Greet someone by name."""
        print(f"[DEBUG] greet() got name={name}")
        print(f"[DEBUG] type(context)={type(context)} repr={repr(context)}")

        # !
        try:
            # Properties (raise if outside request)
            client_id = context.client_id
            request_id = context.request_id
            print("[DEBUG] client_id =", client_id, "request_id =", request_id)
        except Exception as e:
            print(f"[DEBUG] context basic access failed: {e}")

        # !
        scopes = []
        try:
            req = getattr(context.request_context, "request", None)
            if req and getattr(req, "user", None) and hasattr(req.user, "scopes"):
                scopes = list(req.user.scopes)
                print(f"[DEBUG] request.user.scopes = {scopes}")
        except Exception as e:
            print(f"[DEBUG] could not read request.user.scopes: {e}")

        if "admin" not in scopes:
            print(f"[DEBUG] 'admin' scope not present in token scopes: {scopes}")
            return "Error: missing required scope 'admin'"
        
        # !

        return f"Hello, {name}!"
    
    @app.tool()
    def es_log_search_tool(es_query: str, es_limit: int) -> str:
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

        return json.dumps(es_blocks)

    
    @app.tool()
    def chroma_policy_search_tool(chroma_query: str, chroma_limit: int = 5) -> str:
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

        return " ".join(chroma_blocks)

    return app


@click.command()
@click.option("--port", default=8002, help="Port to listen on")
@click.option("--auth-server", default="http://localhost:9001", help="Authorization Server URL")
@click.option(
    "--transport",
    default="streamable-http",
    type=click.Choice(["sse", "streamable-http"]),
    help="Transport protocol to use ('sse' or 'streamable-http')",
)
@click.option(
    "--oauth-strict",
    is_flag=True,
    help="Enable RFC 8707 resource validation",
)
def main(port: int, auth_server: str, transport: Literal["sse", "streamable-http"], oauth_strict: bool) -> int:
    """
    Run the MCP Resource Server.

    This server:
    - Provides RFC 9728 Protected Resource Metadata
    - Validates tokens via Authorization Server introspection
    - Serves MCP tools requiring authentication

    Must be used with a running Authorization Server.
    """
    logging.basicConfig(level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S", format="%(asctime)s %(levelname)s %(message)s")

    try:
        # Parse auth server URL
        auth_server_url = AnyHttpUrl(auth_server)

        # Create settings
        host = "localhost"
        server_url = f"http://{host}:{port}"
        settings = ResourceServerSettings(
            host=host,
            port=port,
            server_url=AnyHttpUrl(server_url),
            auth_server_url=auth_server_url,
            auth_server_introspection_endpoint=f"{auth_server}/introspect",
            oauth_strict=oauth_strict,
        )
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Make sure to provide a valid Authorization Server URL")
        return 1

    try:
        mcp_server = create_resource_server(settings)

        logger.info(f"🚀 MCP Resource Server running on {settings.server_url}")
        logger.info(f"🔑 Using Authorization Server: {settings.auth_server_url}")

        # Run the server - this should block and keep running
        mcp_server.run(transport=transport)
        logger.info("Server stopped")
        return 0
    except Exception:
        logger.exception("Server error")
        return 1


if __name__ == "__main__":
    main()  # type: ignore[call-arg]
