# app/services/anomaly_service.py
import os
import json
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta

from ..extensions import db
from ..model import Anomaly
from app.controllers.rag_controller import es_search, strip_json_markdown, ask_llm, _g
from app.utils.metrics import LLMRunMetrics, count_tokens
from app.utils.policy import build_policy_context_for_prompt

from app.services.ml_inference import AlphaDetector

if not load_dotenv(os.path.join(os.path.dirname(__file__), '../.env')):
    print("[WARNING] No .env file found in the directory")

LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-r1")
logger = logging.getLogger(__name__)

def explain_anomaly_with_llm(log_event: dict, context: str) -> dict:
    """
    Substitui a antiga função 'classify_events_with_rag'. 
    Agora apenas exige RCA (Root Cause Analysis) sobre UM log já detetado como anómalo.
    """
    prompt = f"""
Atua como analista sénior de cibersegurança. O sistema estatístico já sinalizou este log como UMA ANOMALIA.
Log Anómalo: {json.dumps(log_event, ensure_ascii=False)}

Contexto de Políticas da Empresa: {context}

Avalia a causa-raiz e fornece a tua resposta num objeto JSON rigoroso:
{{
  "description": "Breve descrição do que aconteceu",
  "severity": "high" ou "medium",
  "reasoning": "A tua análise técnica detalhada indicando as violações e contexto"
}}
"""
    try:
        text = ask_llm(prompt, LLM_MODEL).strip()
        text = strip_json_markdown(text)
        return json.loads(text)
    except Exception as e:
        logger.error(f"[RCA] Falha na explicação do LLM: {e}")
        return {}


def fetch_recent_events(max_events: int = 100, minutes: int = 15):
    now = datetime.utcnow()
    start = now - timedelta(minutes=minutes)

    query = {
        "query": {"range": {"@timestamp": {"gte": start.isoformat() + "Z", "lte": now.isoformat() + "Z"}}},
        "_source": ["@timestamp", "event.code", "winlog.event_id", "user.name", "message", "log.file.path"],
        "size": max_events
    }
    print(f"[AnomalyService] A buscar eventos recentes desde {start} até {now}...")
    resp = es_search(json.dumps(query))
    print(f"[AnomalyService] Encontrados {len(resp)} eventos recentes.")

    events = []
    for source in resp:  # resp já vem flatten com _id no topo, _source expandido
        print(f"[AnomalyService] Evento encontrado: {source}")
        events.append({
            "es_id": source.get("_id"),
            "timestamp": source.get("@timestamp"),
            "event_code": _g(source, "event.code"),
            "event_id": _g(source, "winlog.event_id"),
            "user": _g(source, "user.name"),
            "message": source.get("message"),
            "path": _g(source, "log.file.path"),
            "source": "winlogbeat"
        })
    return events


def detect_and_create_anomalies():
    """Pipeline reestruturado: Heurística -> SVM -> RCA (LLM)"""
    from .anomaly_service import fetch_recent_events # assumindo que mantêm esta função intata
    events = fetch_recent_events()
    if not events:
        return

    existing_ids = {row.log_id for row in Anomaly.query.with_entities(Anomaly.log_id).all()}
    detector = AlphaDetector()
    
    # Regras Determinísticas Rígidas (Primeira Barreira)
    hard_rules_codes = ["4732", "4728", "4720", "1102", "4719", "7045"]
    policy_context = build_policy_context_for_prompt()
    
    new_anomalies = []

    for evt in events:
        log_id = evt.get("es_id")
        if not log_id or log_id in existing_ids:
            continue
            
        event_code = str(evt.get("event_code"))
        log_text = evt.get("message") or ""
        
        is_suspicious = False
        
        # 1. Triagem Heurística
        if event_code in hard_rules_codes:
            is_suspicious = True
        
        # 2. Triagem Matemática (SVM)
        elif detector.is_anomaly(log_text):
            is_suspicious = True

        # 3. Análise de Causa Raiz pelo LLM (Apenas para o que ativou suspeitas)
        if is_suspicious:
            logger.info(f"Log {log_id} sinalizado. A invocar LLM para RCA...")
            analysis = explain_anomaly_with_llm(evt, policy_context)
            
            if analysis:
                anomaly = Anomaly(
                    log_id=log_id, # type: ignore
                    timestamp=evt.get("timestamp"), # type: ignore
                    source=LLM_MODEL, # type: ignore
                    description=analysis.get("description", "Anomalia estatística detetada"), # type: ignore
                    severity=analysis.get("severity", "medium"), # type: ignore
                    resolved=False, # type: ignore
                    event_code=event_code, # type: ignore
                    user=evt.get("user"), # type: ignore
                    reasoning=analysis.get("reasoning", "Comportamento atípico bloqueado pelo SVM.") # type: ignore
                )
                new_anomalies.append(anomaly)

    if new_anomalies:
        db.session.bulk_save_objects(new_anomalies)
        db.session.commit()
        logger.info(f"{len(new_anomalies)} novas anomalias registadas após filtragem Alpha.")