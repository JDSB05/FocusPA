import chromadb

# Liga ao servidor ChromaDB via HTTP
client = chromadb.HttpClient(host="localhost", port=8000)

# Cria ou acede à coleção
collection = client.get_or_create_collection("documentos")

# Indexa documentos (exemplo)
collection.add(
    documents=[
        "O acesso remoto deve ser feito com VPN.",
        "Autenticação multifator é obrigatória."
    ],
    metadatas=[{"source": "seguranca1.txt"}, {"source": "seguranca2.txt"}],
    ids=["1", "2"]
)

# Consulta
result = collection.query(query_texts=["autenticação"], n_results=1)

print("Resultado:", result["documents"][0])
