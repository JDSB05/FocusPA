# app/services/anomaly_service.py
import json
import logging
from datetime import datetime, timedelta

from ..extensions import db
from ..model import Anomaly
from app.controllers.rag_controller import es_search, strip_json_markdown, ask_llm, _g
from app.utils.metrics import LLMRunMetrics, count_tokens
from app.utils.policy import build_policy_context_for_prompt

logger = logging.getLogger(__name__)


def classify_events_with_rag(question: str, context: str, events_count: int | None = None) -> str:
    prompt = f"""
Classifica os eventos da seguinte questão de segurança: {question}
Com base no seguinte contexto: {context}

Regras:
- Responder apenas em JSON válido.
- Se forem vários eventos: [
    {{
      "id": "...",
      "event_code": "...",
      "user": "...",
      "timestamp": "...",
      "description": "...",
      "severity": "high|medium",
      "reasoning": "..."
    }},
    ...
  ]
- Só devolver eventos que representem risco real (ignorar benign/normal).
- Se não houver dados suficientes para classificar, devolver apenas: null
- Não inventar IDs, não criar eventos. Usa apenas os IDs fornecidos.
- Usa o contexto fornecido (admins e diretórios) apenas para priorizar/filtrar risco — não faças enforcement.
"""
    print(prompt)
    model = "deepseek-coder-v2"
    extras = {
        "events_considered": events_count,
        "question_tokens": count_tokens(question, model),
        "context_tokens": count_tokens(context, model),
        "question_chars": len(question),
        "context_chars": len(context),
    }

    with LLMRunMetrics(
        model=model,
        prompt_text=prompt,
        service="anomaly",
        operation="classify_events",
        extra=extras,
    ) as metrics:
        try:
            print("[Classificação] A enviar prompt ao LLM...")
            text = ask_llm(prompt, model).strip()
            text = strip_json_markdown(text)
            metrics.set_response_text(text)

            if text.lower() == "null":
                return "null"

            parsed = json.loads(text)

            if isinstance(parsed, list):
                valid = all(
                    isinstance(e, dict) and {"id", "description", "severity"} <= set(e.keys())
                    for e in parsed
                )
                if valid:
                    return json.dumps(parsed)
                logger.warning("[Classificação] Lista inválida recebida.")
                return "null"

            logger.warning(f"[Classificação] Tipo inesperado: {type(parsed)}")
            return "null"

        except Exception as e:
            metrics.mark_success(False, str(e))
            logger.error(f"[Classificação] Erro: {e}")
            return "null"


def fetch_recent_events(max_events: int = 100, minutes: int = 15):
    now = datetime.utcnow()
    start = now - timedelta(minutes=minutes)

    query = {
        "query": {"range": {"@timestamp": {"gte": start.isoformat() + "Z", "lte": now.isoformat() + "Z"}}},
        "_source": ["@timestamp", "event.code", "winlog.event_id", "user.name", "message", "log.file.path"],
        "size": max_events
    }
    logger.info(f"[AnomalyService] A buscar eventos recentes desde {start} até {now}...")
    resp = es_search(json.dumps(query))
    logger.info(f"[AnomalyService] Encontrados {len(resp)} eventos recentes.")

    events = []
    for source in resp:  # resp já vem flatten com _id no topo, _source expandido
        logger.debug(f"[AnomalyService] Evento encontrado: {source}")
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
    """Vai buscar eventos recentes, classifica-os em batch com RAG e guarda falhas de segurança."""
    print("[AnomalyService] A iniciar deteção de anomalias...")

    events = fetch_recent_events()
    if not events:
        print("[AnomalyService] Nenhum evento encontrado.")
        return

    existing_ids = {row.log_id for row in Anomaly.query.with_entities(Anomaly.log_id).all()}
    print(f"[AnomalyService] IDs existentes: {len(existing_ids)}")

    event_payload = [
        {
            "id": evt.get("es_id"),
            "event_id": evt.get("event_id"),
            "event_code": evt.get("event_code"),
            "user": evt.get("user"),
            "message": evt.get("message"),
            "path": evt.get("path"),
            "timestamp": evt.get("timestamp"),
        }
        for evt in events if evt.get("es_id")
    ]

    print(f"[AnomalyService] Eventos a classificar: {len(event_payload)}")
    if not event_payload:
        print("[AnomalyService] Nenhum evento válido para classificação.")
        return

    # 1) Pergunta
    policy_question = f"""
Classifica os seguintes eventos de log do Windows.
Devolve apenas as **falhas de segurança confirmadas** (ignora benign/normal).
Formato: array JSON de objetos:
{{"id (igual ao do log que está a ser classificado, não cries nenhum)","event_code","user","timestamp","description","severity","reasoning"}}

Regras fortes:
- Usa os IDs de evento quando existirem:
  - 4732/4728: membro adicionado a *security-enabled (local/global)* (marca MEDIUM/HIGH se grupo = Administrators/Domain Admins).
  - 4720: conta de utilizador criada (MEDIUM/HIGH).
  - 1102: log de auditoria limpo (HIGH).
  - 4719: política de auditoria alterada (HIGH).
  - 7045: serviço instalado (MEDIUM/HIGH).
  - 4625: muitas falhas de logon num curto período (MEDIUM).
- Não devolver “sucesso genérico” sem risco claro.
- Só incluir eventos com risco real; caso contrário, omite-os.

Eventos:
{json.dumps(event_payload, ensure_ascii=False)}
"""
    # 2) Contexto adicional: admins, diretórios sensíveis e custom prompt
    policy_context = f"""
Considera o seguinte contexto para a avaliação (apenas para te orientar, não é uma política de acesso vinculativa):
- Os utilizadores listados como *admins* têm acesso generalista a qualquer diretório; acessos feitos por eles só são anómalos se houver outros sinais fortes.
- Para cada entrada em "diretórios sensíveis", se um utilizador **não** estiver em allowed_users e aceder ao path (prefix-match), tende a ser **mais suspeito**.
- Usernames são case-insensitive. Em allowed_users, * é wildcard.
- Poderás ter ainda umas notas extra fornecidas pelo utilizador. Leva-as também em conta.
- Se não houver match com nenhum diretório sensível, decide pela heurística geral dos eventos/códigos.
{build_policy_context_for_prompt()}
"""
    
    print("[AnomalyService] A enviar prompt ao LLM para classificação...")
    raw = classify_events_with_rag(policy_question, policy_context, events_count=len(event_payload))
    if raw == "null":
        print("[AnomalyService] Nenhuma anomalia detectada pelo LLM.")
        return

    try:
        anomalies_from_llm = json.loads(raw)
    except Exception as e:
        logger.error("[AnomalyService] Erro a interpretar resposta LLM: %s", e)
        return

    new_anomalies = []
    for evt in events:
        log_id = evt.get("es_id")
        match = next((a for a in anomalies_from_llm if a.get("id") == log_id), None)
        if not match or log_id in existing_ids:
            continue

        sev = (match.get("severity") or "").lower()
        if sev not in {"medium", "high"}:
            continue  

        anomaly = Anomaly(
            log_id=log_id, # type: ignore
            timestamp=evt.get("timestamp"), # type: ignore
            source=evt.get("source", "LLM"), # type: ignore
            description=match.get("description", ""), # type: ignore
            severity=match.get("severity", "medium"), # type: ignore
            resolved=False, # type: ignore
            resolved_at=None, # type: ignore
            event_code=match.get("event_code") or evt.get("event_code"), # type: ignore
            user=match.get("user") or evt.get("user"), # type: ignore
            reasoning=match.get("reasoning", "") # type: ignore
        )
        new_anomalies.append(anomaly)
        print(
            f"[AnomalyService] Nova anomalia detectada: {anomaly.description} "
            f"(sev={anomaly.severity}, log_id={log_id})"
        )

    if new_anomalies:
        db.session.bulk_save_objects(new_anomalies)
        db.session.commit()
        print(f"[AnomalyService] {len(new_anomalies)} anomalias guardadas.")
