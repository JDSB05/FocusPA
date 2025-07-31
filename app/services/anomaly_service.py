import json
from datetime import datetime
from ..extensions import db
from ..model import Anomaly
from app.controllers.rag_controller import ask_llm, query_hybrid_rag
from datetime import datetime, timedelta
from dateutil import parser
from app.services.elastic import es

def classify_events_with_rag(events: list[dict]) -> list[dict]:
    """
    Envia vários eventos de uma vez para a pipeline RAG e espera
    um array JSON de classificação na mesma ordem.
    """
    # Extrai só as mensagens
    messages = [evt["message"] for evt in events]

    # Prepara o prompt que a query_hybrid_rag vai usar internamente
    # (ela já monta o contexto ES + Chroma)
    batch_prompt = (
        "Você receberá um array de logs (strings). "
        "Para cada log, responda em JSON com os campos:\n"
        '  {"anomaly": true|false, "description": "...", "severity": "low|medium|high"}\n'
        "Retorne um array JSON com esses objetos na MESMA ordem.\n\n"
        f"{json.dumps(messages, ensure_ascii=False)}"
    )

    # Chama a pipeline RAG
    resp = query_hybrid_rag(batch_prompt)

    # Tenta fazer o parse do JSON de volta
    try:
        return json.loads(resp)
    except (json.JSONDecodeError, TypeError):
        # Em caso de falha, retorna fallback “sem anomalias”
        return [{"anomaly": False, "description": m, "severity": "low"} for m in messages]
    
def fetch_recent_events(window_minutes: int = 60, max_events: int = 100):
    """
    Busca no Elasticsearch os logs dos últimos `window_minutes` minutos
    e retorna uma lista de dicts contendo mensagem, timestamp e fonte.
    """
    # Define o intervalo de tempo
    now = datetime.now()
    start = now - timedelta(minutes=window_minutes)

    # Monta a consulta Elasticsearch para buscar logs recentes
    try:
        resp = es.search(
            index="winlog-*",
            size=max_events,
            query={
                "range": {
                    "@timestamp": {
                        "gte": start.isoformat(),
                        "lte": now.isoformat()
                    }
                }
            },
            sort=[{"@timestamp": {"order": "desc"}}],
            _source=["message", "@timestamp"] # type: ignore
        )
    except Exception as e:
        print(f"[WARN] [Elasticsearch] falha ao buscar eventos recentes: {e}")
        return []

    hits = resp.get("hits", {}).get("hits", [])
    events = []
    for hit in hits:
        src = hit.get("_source", {})
        ts_raw = src.get("@timestamp")
        try:
            ts = parser.isoparse(ts_raw)
        except Exception:
            ts = datetime.utcnow()
        events.append({
            "message": src.get("message", ""),
            "timestamp": ts,
            "source": "elasticsearch"
        })

    print(f"[INFO] [fetch_recent_events] retornou {len(events)} eventos dos últimos {window_minutes} minutos")
    return events

def detect_and_create_anomalies():
    print("[INFO] [AnomalyService] Detectando e criando anomalias...")
    events = fetch_recent_events()
    if not events:
        return

    # 1) Classifica todos de uma vez
    results = classify_events_with_rag(events)
    # 2) Para cada resultado, insere se for anomalia
    for evt, result in zip(events, results):
        if result.get("anomaly"):
            anomaly = Anomaly(
                timestamp   = evt["timestamp"], # type: ignore
                source      = evt.get("source", "llm"), # type: ignore
                description = result["description"], # type: ignore
                severity    = result.get("severity", "medium") # type: ignore
            )
            db.session.add(anomaly)
            print(f"[INFO] [AnomalyService] Anomalia detectada: "
                  f"{anomaly.description} (gravidade: {anomaly.severity})")
    db.session.commit()