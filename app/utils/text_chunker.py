from datetime import datetime
import json
from app.controllers.rag_controller import ask_llm, build_es_query_from_events, strip_json_markdown
import os

LLM_MODEL_LIGHT = os.environ.get("LLM_MODEL_LIGHT", "deepseek-coder-v2")

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

def get_h_questions(chunks : list[str]) -> list[str]:
    """Gera perguntas hipotéticas para uma lista de chunks."""
    return [hypothetical_question(chunk) for chunk in chunks]

def hypothetical_question(chunk: str, model: str = LLM_MODEL_LIGHT, words_limit: int = 100) -> str:
    """Gera uma pergunta hipotética para um chunk de texto, para melhorar embeddings."""
    prompt = (
        "Dado o seguinte excerto de um texto de política, gera uma pergunta concisa e específica que capte o seu ponto principal. "
        " - A pergunta deve ser clara e focada, adequada para recuperar esta informação posteriormente via RAG e não deve exceder {words_limit} palavras. "
        " - A pergunta deve ser gerada utilizando o idioma detetado no excerto. Em caso de dúvida, utiliza português de Portugal. "
        " - Inclui no final da pergunta o índice do capítulo, secção ou subseção mencionado, se disponível no excerto. "
        "     Exemplo: Quais são as medidas de proteção de dados descritas na Secção 4.2? (Secção 4.2, Secção 4.1, Capítulo 3)"
        "\n\n"
        f"Excerto do Texto da Política:\n{chunk}\n\n"
        "Pergunta Hipotética:"
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
        return [f"Name: {name}\nFilename: {filename}\nPergunta hipotética:{h}\n{c}" for c, h in zip(chunks, h_questions)]

def nat_lang_to_es(chunk: str) -> str:
    """Converte um chunk de uma politica em linguagem natural numa query para o ES + raciocínio usado."""
    
    prompt = f"""
Considerando o excerto de política abaixo, gera uma query de pesquisa para o Elasticsearch que possa ser usada para encontrar eventos que não estejam em conformidade com esta política.
Regras:
- Se a política incluir vários valores para um campo, usar "terms" (plural) em vez de "term".
- Colocar filtros temporais (intervalos de datas) **sempre dentro de "range"**, nunca diretamente como chave.
  Exemplo correto:
  {{ "range": {{ "@timestamp": {{ "gte": "...", "lte": "..." }} }} }}
- Não deves aplicar filtros temporais de forma a diminuir o conjunto de resultados, a menos que a política especifique claramente um intervalo de tempo.
- Para extraír a hora de um timestamp, usa: doc['@timestamp'].value.getHour() 
- Quando aplicares filtros temporais, usar dentro de "filter" e não "must".
- Devolver JSON válido e depois uma explicação breve (1 a 3 frases) do raciocínio, conforme a formatação do exemplo abaixo (separar JSON e raciocínio com "#####"):
    {{ "query": {{ ... }} }}
    #####
    <Explicação do raciocínio>
- Se a política específicar um intervalo de tempo em que apenas horas são mencionadas, considera que se aplica todos os dias.
- Ignorar qualquer menção acerca de severidade, níveis de alerta.
- Não menciones estas regras, aplica-as apenas.
- Se a política for muito vaga e não houver dados suficientes para gerar a query, devolver apenas: null
- No raciocínio, utilizar a linguagem detetada no excerto. Em caso de dúvida, utilizar português de Portugal.
- Não comentar em nenhuma parte do json.

Campos comuns que podes usar: 
- "@timestamp" (range)
- "event.code"
- "winlog.event_id"
- "user.name"
- "access_mask"
- "log.level"
- "log_name"

Hoje é {datetime.utcnow().isoformat()}Z.

Excerto da política:
{chunk}

Resposta (JSON + raciocínio ou null):
"""
    try:
        llm_answer = ask_llm(prompt, LLM_MODEL_LIGHT).strip()
        llm_answer_s = llm_answer.split("#####")

        # Caso a resposta seja null ou no formato invalido returnar strings vazias
        if llm_answer.lower() == "null" or len(llm_answer_s) != 2:
            return "", ""
        
        es_query, reasoning = llm_answer_s
        es_query = strip_json_markdown(es_query)
        reasoning = strip_json_markdown(reasoning)

        try:
            parsed = json.loads(es_query)
        except Exception:
            print(f"[WARN] [NAT_LANG_TO_ES] Resposta não era JSON: {es_query}...")
            return "", ""

        if isinstance(parsed, list):
            return json.dumps(build_es_query_from_events(parsed)), reasoning

        if isinstance(parsed, dict):
            return json.dumps(parsed), reasoning

        else:
            print(f"[WARN] [NAT_LANG_TO_ES] Tipo inesperado: {type(parsed)}")
            return "", ""

    except Exception as e:
        print(f"[ERROR] [NAT_LANG_TO_ES] {e}")
        return "", ""
