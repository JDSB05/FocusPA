"""
Controller para visualizar logs do Winlogbeat no Elasticsearch e
criar anomalias manualmente a partir desses logs.
"""
from math import ceil
from flask import render_template, request, jsonify, flash

from app.controllers.rag_controller import es_search
from ..extensions import db
from ..model import Anomaly
from ..services.elastic import es 

def list_logs():
    """
    Lista paginada de logs do Winlogbeat (via es_search).
    Permite passar query_text, time_from, time_to via query string.
    """
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    # parâmetros de pesquisa
    time_from = request.args.get("from")    # ex: "2025-08-01T00:00:00Z"
    time_to   = request.args.get("to")

    # chamar helper
    query_text = request.args.get("q")
    if query_text:
        all_hits = es_search(query_text, time_from=time_from, time_to=time_to, size=10000)
    else:
        # query base explícita: tudo
        all_hits = es_search("{}", time_from=time_from, time_to=time_to, size=10000)


    # paginação em memória (podes depois passar from/size ao es_search para ser direto)
    total = len(all_hits)
    start = (page - 1) * per_page
    end = start + per_page
    logs = all_hits[start:end]

    # normalizar campos
    normalized = []
    for h in logs:
        print(h)
        print(h.get("_index"))
        normalized.append({
            "_id": h.get("_id"),
            "_index": h.get("_index"),
            "timestamp": h.get("@timestamp"),
            "event_id": h.get("event", {}).get("code") or h.get("winlog", {}).get("event_id"),
            "user": (h.get("user") or {}).get("name"),
            "message": h.get("message"),
            "logfile": (h.get("log") or {}).get("file", {}).get("path"),
        })

    pages = ceil(total / per_page) if per_page else 1
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_prev": page > 1,
        "has_next": page < pages,
        "prev_num": page - 1,
        "next_num": page + 1,
    }

    return render_template(
        "pages/logs.html",
        logs=normalized,
        pagination=pagination,
        query=query_text,
        time_from=time_from,
        time_to=time_to,
    )


def create_anomaly_from_log():
    """
    Cria uma Anomaly a partir de um documento do ES.
    Espera JSON: { "index": "<index_name>", "id": "<doc_id>" }
    """
    data = request.get_json(silent=True) or {}
    index = data.get("index")
    doc_id = data.get("" \
    "id")

    if not index or not doc_id:
        flash("Pedido inválido (index/id em falta).", "Erro")
        print("[LogController] create_anomaly_from_log: missing index/id")
        return jsonify({"error": "missing index/id"}), 400

    # Obter o documento original
    try:
        doc = es.get(index=index, id=doc_id)  # type: ignore
    except Exception:
        flash("Não foi possível obter o log no Elasticsearch.", "Erro")
        print("[LogController] create_anomaly_from_log: es.get failed")
        return jsonify({"error": "es.get failed"}), 404

    src = doc.get("_source", {})
    event_code = (src.get("event") or {}).get("code")
    provider = (src.get("winlog") or {}).get("provider_name")
    message = (src.get("message") or "")

    description = f"[ES:{index}/{doc_id}] {provider or '-'} | event={event_code or '-'} | {message}"

    anomaly = Anomaly(
        source="elastic:winlogbeat",
        description=description,
        severity="low",
        log_id=doc_id,
        
    )
    db.session.add(anomaly)
    db.session.commit()

    flash("Anomalia criada manualmente a partir de log do ES.", "Sucesso")
    return jsonify({"message": "created", "anomaly_id": anomaly.id}), 201
