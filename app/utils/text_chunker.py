def split_into_word_chunks(text: str, chunk_words: int = 800, overlap: int = 80):
    """
    Divide o texto em blocos de ~chunk_words com overlap.
    800/80 ≈ alvo 500–1000 palavras conforme pediste.
    """
    words = text.split()
    if not words:
        return []

    step = max(chunk_words - overlap, 1)
    chunks = []
    i = 0
    n = len(words)
    while i < n:
        chunk = words[i:i + chunk_words]
        if not chunk:
            break
        chunks.append(" ".join(chunk))
        if i + chunk_words >= n:
            break
        i += step
    return chunks
