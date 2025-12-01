# MCP com Autenticação (OAuth) — Guia de Implementação

Este guia descreve a implementação do MCP com `autenticação OAuth`, separando os papéis de Authorization Server (AS) e Resource Server (RS) e providenciando um cliente com suporte OAuth a partir do qual são chamadas as tools.

A maioria dos ficheiros necessários encontra-se em `/mcp_files`. Adicionalmente, foi criado o controlador Flask `/app/controllers/auth_mcp.py` para receber callbacks OAuth no contexto da aplicação web.

Os ficheiros foram adaptados do [exemplo](https://github.com/modelcontextprotocol/python-sdk/tree/main/examples/servers/simple-auth#readme) presente no [SDK oficial](https://github.com/modelcontextprotocol/python-sdk) do MCP em Python.

Links que talvez possam ser úteis: 

- MCP auth: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- SDK em Python: https://github.com/modelcontextprotocol/python-sdk

## Componentes

- Authorization Server (AS)
  - `mcp_files/auth_server.py`
  - Implementa endpoints de:
    - Registo de cliente
    - Autorização (gera URL de login simples)
    - Callback de login
    - Introspeção de tokens (RFC 7662) em `/introspect`
  - Baseado em `SimpleOAuthProvider` com credenciais:
    - `admin:admin` (scopes: `user admin`)
    - `user:user` (scopes: `user`)

- Resource Server (RS) - MCP Server
  - `mcp_files/secure_mcp_server.py`
  - Implementa:
    - Verificação de tokens por introspeção (`token_verifier.py`)
    - Ferramentas MCP protegidas por scope:
      - `greet` (exemplo de uma tool que exige scope `admin`)
      - `es_log_search_tool` (Elasticsearch)
      - `chroma_policy_search_tool` (ChromaDB)

- MCP Client com OAuth
  - `mcp_files/secure_mcp_client.py`
  - Usa `OAuthClientProvider` e `InMemoryTokenStorage`
  - Automatiza:
    1) Registo/metadata cliente
    2) Obtenção do URL de login
    3) Submissão de credenciais
    4) Receção do authorization code via callback HTTP local (/callback/\<role>) [ver](../app/controllers/auth_mcp.py).
    5) Troca por token e conexão ao RS via Streamable HTTP

- Callback OAuth na aplicação Flask
  - `app/controllers/auth_mcp.py`
  - Endpoint: `/mcp/callback/<role>`
  - Recebe `code` e `state` e armazena em `mcp_client.role_data[role]["callback_data"]` para que o MCP Client finalize o fluxo OAuth.

## Como correr?
- Authentication Server: `python .\mcp_files\auth_server.py`
- MCP Server: `python .\mcp_files\secure_mcp_server.py`
- FocusPA (como normalmente): `python -m app.app`

## Teste de scopes
- Ir a [rag.py](../app/routes/rag.py)
- Descomentar: `response = await mcp_client.call_greet_tool(name="FocusPA", role=role)`
- Comentar: `response = await mcp_client.query_rag_with_mcp_tools(question=question, messages=messages)
`
- Dar login com username user e escrever no chat bot
- Deve dar "Error: missing required scope 'admin'"
- Dar login com outro username e escrever no chat bot
- Deve dar "Hello, FocusPA!"

## Adaptações feitas do exemplo
Para visualizar melhor as mudanças do exemplo, sugiro fazer-se um `diff` entre os ficheiros do projeto (cima) e os do sdk (baixo)

- mcp_files/auth_server.py
- \<path_do_sdk>/examples/servers/simple-auth/mcp_simple_auth/auth_server.py

---

- mcp_files/secure_mcp_client.py
- \<path_do_sdk>/examples/clients/simple-auth-client/mcp_simple_auth_client/main.py

---

- mcp_files/secure_mcp_server.py
- \<path_do_sdk>/examples/servers/simple-auth/mcp_simple_auth/server.py

---

- mcp_files/simple_auth_provider.py
- \<path_do_sdk>/examples/servers/simple-auth/mcp_simple_auth/simple_auth_provider.py

---

- mcp_files/token_verifier.py
- \<path_do_sdk>/examples/servers/simple-auth/mcp_simple_auth/token_verifier.py

