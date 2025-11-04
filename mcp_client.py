"""
Ficheiro para testes e desenvolvimento do cliente MCP.
Adaptado a partir do exemplo do repo https://github.com/modelcontextprotocol/python-sdk:
    examples/snippets/clients/streamable_basic.py
"""

import asyncio

import mcp
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import ollama

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
    

async def main():
    # Connect to a streamable HTTP server
    async with streamablehttp_client("http://localhost:9400/mcp") as (
        read_stream,
        write_stream,
        _,
    ):
        # Create a session using the client streams
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the connection
            await session.initialize()
            # List available tools
            mcp_tools = await session.list_tools()
            print(f"Available tools: {[tool.name for tool in mcp_tools.tools]}")
            
            olama_tools = [mcp_to_ollama(tool) for tool in mcp_tools.tools]
            
            response =  ollama.chat(
                model="gpt-oss:120b",
                messages=[
                    {"role": "user", "content": "Do you know if there was any anomaly in september 5th?"}
                ],
                tools=olama_tools,
                stream=False,
            )

            print(f"Response: {response}")

            for tool in mcp_tools.tools:
                print(f"Tool: {tool.name}")
                if tool.description:
                    print(f"   {tool.description}")
                if tool.inputSchema:
                    print(f"   {tool.inputSchema}")


if __name__ == "__main__":
    asyncio.run(main())
