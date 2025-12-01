#!/usr/bin/env python3
"""
Simple MCP client example with OAuth authentication support.

This client connects to an MCP server using streamable HTTP transport with OAuth.

"""

import asyncio
from datetime import datetime
import os
import threading
import time
import webbrowser
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import mcp
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

import ollama
import requests

from flask_login import current_user

def mcp_client_init():
    import os
    """Main entry point."""
    # Default server URL - can be overridden with environment variable
    # Most MCP streamable HTTP servers use /mcp as the endpoint
    server_url = os.getenv("MCP_SERVER_PORT", 8002)
    transport_type = os.getenv("MCP_TRANSPORT_TYPE", "streamable-http")
    server_url = (
        f"http://localhost:{server_url}/mcp"
        if transport_type == "streamable-http"
        else f"http://localhost:{server_url}/sse"
    )

    # print("🚀 Simple MCP Auth Client")
    # print(f"Connecting to: {server_url}")
    # print(f"Transport type: {transport_type}")

    # Start connection flow - OAuth will be handled automatically
    mcp_client = SimpleAuthClient(server_url, transport_type)
    if mcp_client is not None:
        print("[INFO] [MCP] Client initialized successfully.")
    else:
        print("[ERROR] [MCP] Failed to initialize client.")

    return mcp_client

def mcp_to_ollama(mcp_tool: mcp.Tool):
    """
    Convert an MCP tool into an Ollama tool.
    """

    tool = {
        "name": mcp_tool.name,
        "description": mcp_tool.description,
        "parameters": mcp_tool.inputSchema,
    }

    return {"type": "function", "function": tool}



class InMemoryTokenStorage(TokenStorage):
    """Simple in-memory token storage implementation."""

    def __init__(self):
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        # print(f"\n\n[DEBUG] TOKEN SET TO {tokens}")
        self._tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info = client_info


class SimpleAuthClient:
    """Simple MCP client with auth support."""

    def __init__(self, server_url: str = "http://localhost:8002/mcp"):
        self.server_url = server_url
        
        # !!! No futuro isto deve ser substituído por um mecanismo mais seguro 👍 !!!
        self.role_data = {
            "admin": {"username": "admin", "password": "admin", "scopes": ["user", "admin"], "oauth_auth": None, "token_storage": InMemoryTokenStorage(), 
                      "callback_data": {"authorization_code": None, "state": None, "error": None}},
            "user": {"username": "user", "password": "user", "scopes": ["user"], "oauth_auth": None, "token_storage": InMemoryTokenStorage(), 
                     "callback_data": {"authorization_code": None, "state": None, "error": None}},
        }
        # !!! No futuro isto deve ser substituído por um mecanismo mais seguro 👍 !!!

    def with_session(func):
        async def _connect(self, *args, **kwargs):
            result = None
            if "role" not in kwargs:
                role = "user"
            else:
                role = kwargs["role"]
            
            # Inicializa OAuth caso ainda nao o tenha feito
            if self.role_data[role]["oauth_auth"] is None:
                self.role_data[role]["oauth_auth"] = await self.connect(role=role)

            if self.role_data[role]["oauth_auth"] is None:
                raise Exception("OAuth authentication not initialized.")

            try:
                print("📡 Opening StreamableHTTP transport connection with auth...")
                async with streamablehttp_client(
                    url=self.server_url,
                    auth=self.role_data[role]["oauth_auth"],
                    timeout=timedelta(seconds=60),
                ) as (read_stream, write_stream, get_session_id):
                    """Run the MCP session with the given streams."""
                    # print("🤝 Initializing MCP session...")
                    async with ClientSession(read_stream, write_stream) as mcp_session:
                        # self.session = session
                        # print("⚡ Starting session initialization...")
                        await mcp_session.initialize()
                        print("✨ Session initialization complete!")

                        print(f"✅ Connected to MCP server at {self.server_url}")
                        if get_session_id:
                            session_id = get_session_id()
                            if session_id:
                                # print(f"Session ID: {session_id}")
                                result = await func(self, mcp_session, *args, **kwargs)
            except Exception as e:
                print(f"[MCP] [ERROR] Connection error: {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                # print("[MCP] Connection closed.")
                return result
        
        return _connect

    def wait_for_callback(self, role: str, timeout=300):
        """Wait for OAuth callback with timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.role_data[role]["callback_data"]["authorization_code"]:

                # print("GOT THE AUTHORIZATION CODE: ", end="")
                # print(self.role_data[role]["callback_data"]["authorization_code"])
                return self.role_data[role]["callback_data"]["authorization_code"]

            elif self.role_data[role]["callback_data"]["error"]:

                # print("GOT THE ERROR", end="")
                raise Exception(f"OAuth error: {self.role_data[role]['callback_data']['error']}")
            
            time.sleep(0.1)
        raise Exception("Timeout waiting for OAuth callback")

    async def connect(self, role: str):
        """Connect to the MCP server."""
        print(f"🔗 Attempting to connect to {self.server_url}...")

        try:

            async def callback_handler() -> tuple[str, str | None]:
                """Wait for OAuth callback and return auth code and state."""
                # print("⏳ Waiting for authorization callback...")

                auth_code = self.wait_for_callback(role=role, timeout=15)
                return auth_code, self.role_data[role]["callback_data"]["state"]

            client_metadata_dict = {
                "client_name": "Simple Auth Client",
                "redirect_uris": [f"http://127.0.0.1:5000/mcp/callback/{role}"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
                "scope": " ".join(self.role_data[role]["scopes"]),
            }

            async def _default_redirect_handler(authorization_url: str) -> None:
                """Drive the AS login and then trigger the local callback explicitly."""
                try:
                    import requests
                    s = requests.Session()

                    # 1) Ask AS for redirect_uri and state
                    response = s.get(authorization_url, timeout=10)
                    response.raise_for_status()
                    response_json = response.json()
                    redirect_uri = response_json.get("redirect_uri")
                    state = response_json.get("state")
                    # print(f"[INFO] [MCP] response_json: {response_json}")

                    # 2) Post credentials to AS login/callback
                    data = {
                        "username": self.role_data[role]["username"],
                        "password": self.role_data[role]["password"],
                        "state": state,
                    }
                    post_response = s.post(redirect_uri, data=data, allow_redirects=False, timeout=10)
                    print(f"Posted to {redirect_uri}, response status: {post_response.status_code}")

                    # 3) If AS returns redirect to our local callback, follow it
                    if post_response.is_redirect or post_response.status_code in (302, 303):
                        loc = post_response.headers.get("Location")
                        # print(f"[DEBUG] [MCP] Following redirect to {loc}")
                        if loc:
                            s.get(loc, timeout=10)
                        else:
                            print("⚠️ No Location header on AS redirect.")
                except Exception as e:
                    print(f"❌ Error occurred while handling redirect: {e}")
                    # print("Trying to reconnect...")

            return OAuthClientProvider(
                server_url=self.server_url.replace("/mcp", ""),
                client_metadata=OAuthClientMetadata.model_validate(client_metadata_dict),
                storage=self.role_data[role]["token_storage"],
                redirect_handler=_default_redirect_handler,
                callback_handler=callback_handler,
            )
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            import traceback
            traceback.print_exc()  

    @with_session
    async def _list_tools(self, mcp_session):
        tools = await mcp_session.list_tools()
        # print(f"\n\nDEBUG: {tools}")
        return tools

    @with_session
    async def call_greet_tool(self, mcp_session, name: str, role: str = "user"):
        print("[INFO] [MCP SERVER] Calling greet tool...")
        tool_response = await mcp_session.call_tool("greet", {"name": name})
        return tool_response.content[0].text

    @with_session
    async def query_rag_with_mcp_tools(
        self,
        mcp_session,
        question: str,
        messages: list[dict] | None = None,   # histórico do browser
        hist_size: int = 12,
    ):
        """
        Versão com recurso a tools de MCP
        Envia pergunta para o LLM com tools do server MCP.
        """
        print("[INFO] [MCP SERVER] Starting RAG query with MCP tools.")
        # Pergunta efetiva a usar no RAG (se question vier vazio, tenta última do user)
        def _last_user_question(msgs):
            if not isinstance(msgs, list):
                return ""
            for m in reversed(msgs):
                if (m.get("role") or "").lower() == "user" or (m.get("role") or "").lower() == "tool":
                    txt = (m.get("content") or "").strip()
                    if txt:
                        return txt
            return ""

        final_question = (question or "").strip() or _last_user_question(messages)

        norm_msgs = []
        if isinstance(messages, list):
            for m in messages[-hist_size:]:
                role = (m.get("role") or "user").lower()
                content = (m.get("content") or "").lstrip("\u0001")
                if content:
                    norm_msgs.append({"role": role, "content": content})


        # Garante que a última mensagem do histórico é a 'final_question' (do user)
        if not norm_msgs or norm_msgs[-1]["role"] != "user":
            norm_msgs.append({"role": "user", "content": final_question})

        system_ctx = (
            "Instruções:\n"
            "- Responde de forma técnica e sucinta, como perito em Windows Event Logs (segurança/auditoria).\n"
            "- Usa apenas o contexto acima. Se faltar informação, diz explicitamente o que falta.\n"
            f"- Hoje é {datetime.utcnow().isoformat()}Z.\n"
        )

        # ---- Compose mensagens para o LLM (SYSTEM + histórico do browser) ----
        combined_messages = [{"role": "system", "content": system_ctx}] + norm_msgs

        # Faz-se uma busca para identificar as tools disponiveis no server MCP
        if mcp_session is None:
            olama_tools = []
        else:
            mcp_tools = await mcp_session.list_tools()
            print(f"[INFO] [MCP SERVER] Available tools: {[tool.name for tool in mcp_tools.tools]}")
            olama_tools = [mcp_to_ollama(tool) for tool in mcp_tools.tools]

        # E feita a pergunta inicial, apresentando as tools disponiveis
        response = ollama.chat(
            model="qwen2.5:32b",
            messages=combined_messages,
            stream=False,
            think=False,
            tools=olama_tools,
        )

        # print(f"Ollama response: {response.message.content}")

        # combined_messages.append({"role": response.message.role, "content": response.message.content, "thinking": response.message.thinking})
        # A cada tool chamada, invoca-se o MCP para obter o seu resultado
        if response.message.tool_calls:
            # print(f"[INFO] [MCP SERVER] Tools called: {[tool_call.function.name for tool_call in response.message.tool_calls]}")
            for tool_call in response.message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments

                func_res = await mcp_session.call_tool(tool_name, tool_args)

                print(f"[INFO] [MCP SERVER] tool called: {tool_name} with arguments: {tool_args[:30] if len(tool_args) > 30 else tool_args}")
                
                result = " ".join([f.text for f in func_res.content if isinstance(f, mcp.types.TextContent)])
                combined_messages.append({"role": "tool", "name": tool_name, "content": result})

        # Caso nao haja nenhuma tool chamada, devolve a resposta diretamente
        else:
            return response.message.content

        response = ollama.chat(
            model="qwen2.5:32b",
            messages=combined_messages,
            stream=False,
            think=False,
        )

        combined_messages.append({"role": response.message.role, "content": response.message.content, "thinking": response.message.thinking})

        if response.message.content != "":
            return response.message.content
        else:
            # Se a ultima mensagem nao tiver conteudo, devolver resultado das tools chamadas ao utilizador
            return "tool results: " + "\n----\n".join([f'{m["name"]}:\n{m["content"]}' for m in combined_messages if m["role"] == "tool"])

