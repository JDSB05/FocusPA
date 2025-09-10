from app.controllers.rag_controller import ask_llm, strip_json_markdown
import os

LLM_MODEL_LIGHT = os.environ.get("LLM_MODEL_LIGHT", "deepseek-coder-v2")

def split_into_word_chunks(text: str, chunk_words: int = 800, overlap: int = 80, use_h_quest: bool = False):
    """
    Divide o texto em blocos de ~chunk_words com overlap.
    800/80 ≈ alvo 500–1000 palavras conforme pediste.
    """
    words = text.split()
    if not words:
        return []

    step = max(chunk_words - overlap, 1)
    chunks = []
    h_questions = []
    i = 0
    n = len(words)
    while i < n:
        chunk = words[i:i + chunk_words]
        if not chunk:
            break

        chunk = " ".join(chunk)
        chunks.append(chunk)
        if use_h_quest:
            h_questions.append(hypothetical_question(chunk))

        if i + chunk_words >= n:
            break
        i += step
    return chunks, h_questions

def hypothetical_question(chunk: str, model: str = LLM_MODEL_LIGHT, words_limit: int = 100) -> str:
    """Gera uma pergunta hipotética para um chunk de texto, para melhorar embeddings."""
    prompt = (
        "Given the following excerpt from a policy text, generate a concise and specific question that captures its main point. "
        " - The question should be clear and focused, suitable for retrieving this information later via RAG and should not exceed {words_limit} words. "
        " - The question should be generated using the language detected in the excerpt. If in doubt, use English. "
        " - Include at the end of the question the chapter, section, or subsection index mentioned if available in the excerpt. "
        "     Example: What are the data protection measures outlined as per Section 4.2? (Section 4.2, Section 4.1, Chapter 3)"
        "\n\n"
        f"Policy Text Excerpt:\n{chunk}\n\n"
        "Hypothetical Question:"
    )
    try:
        h_question = ask_llm(prompt, model).strip()
        h_question = strip_json_markdown(h_question)

        return h_question
    except Exception as e:
        print(f"[WARN] Erro ao gerar pergunta hipotética: {e}")
    
    return "_"

def get_embedding_chunks(name: str, filename: str, chunks: list[str], h_questions: list[str]) -> list[list[float]]:
    """Formata os chunks para embedding, incluindo metadados e pergunta hipotética."""
    
    if len(h_questions) == 0:
        return [f"Name: {name}\nFilename: {filename}\n{c}" for c in chunks]
    else:
        formated_chunks = [f"Name: {name}\nFilename: {filename}\nPergunta hipotética:{h}\n{c}" for c, h in zip(chunks, h_questions)]

    return formated_chunks
