import os
import chromadb


chroma = chromadb.HttpClient(
    host=os.environ.get("CHROMA_HOST", "localhost"),
    port=int(os.environ.get("CHROMA_PORT", "8000")),
)

if not chroma.heartbeat():
    print("[ERROR] ChromaDB is not reachable. Please check your configuration.")
else:
    print("[INFO] ChromaDB is connected and operational.")



