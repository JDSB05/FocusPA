from sentence_transformers import SentenceTransformer

# Carregado uma vez, reutilizado
_model = SentenceTransformer("all-MiniLM-L6-v2")

def embed(texts):
    """Recebe str ou lista[str], devolve lista[list[float]]"""
    if isinstance(texts, str):
        texts = [texts]
    return _model.encode(texts, convert_to_numpy=True).tolist()
