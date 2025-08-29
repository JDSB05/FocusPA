"""
Controller para visualizar logs do Winlogbeat no Elasticsearch e
criar anomalias manualmente a partir desses logs.
"""
from flask import render_template, request, jsonify, flash
from elasticsearch import helpers
from flask_login import current_user
from app.services.elastic import es
from ..extensions import db
from ..model import Anomaly
from ..services.policy_linker import link_anomaly_to_policy_chunks
from ..utils.pagination import paginate


def es_search_paginated(index="winlog-*", query=None, time_from=None, time_to=None, page_size=1000, page=1):
    """
    Busca logs no Elasticsearch com paginação (sem limite de 10k).
    """
    if query is None:
        query = {"match_all": {}}

    body = {"query": query}

    # filtros temporais opcionais
    if time_from or time_to:
        range_filter = {"range": {"@timestamp": {}}}
        if time_from:
            range_filter["range"]["@timestamp"]["gte"] = time_from
        if time_to:
            range_filter["range"]["@timestamp"]["lte"] = time_to
        body.setdefault("query", {}).setdefault("bool", {}).setdefault("filter", []).append(range_filter)

    # calcular offsets
    start = (page - 1) * page_size
    end = start + page_size

    results = []
    total = 0
    for i, hit in enumerate(
        helpers.scan(client=es, index=index, query=body, size=page_size, scroll="2m"),
        start=0
    ):
        if i >= start and i < end:
            results.append(hit["_source"] | {"_id": hit["_id"], "_index": hit["_index"]})
        total += 1
        if i >= end:
            break

    return results, total


def list_logs():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    provider = request.args.get("provider")
    level = request.args.get("level")
    event_code = request.args.get("event_code")
    q_text = request.args.get("q")
    time_from = request.args.get("from")
    time_to = request.args.get("to")

    filters = []
    if provider:
        filters.append({"term": {"winlog.provider_name.keyword": provider}})
    if level:
        filters.append({"term": {"log.level.keyword": level}})
    if event_code:
        filters.append({"term": {"event.code": event_code}})
    if q_text:
        filters.append({"match": {"message": q_text}})
    if time_from or time_to:
        range_filter = {"range": {"@timestamp": {}}}
        if time_from:
            range_filter["range"]["@timestamp"]["gte"] = time_from
        if time_to:
            range_filter["range"]["@timestamp"]["lte"] = time_to
        filters.append(range_filter)

    # Só executa query se houver filtros
    if not filters:
        _, pagination, start_page, end_page, args = paginate([], page=page, per_page=per_page, total=0)
        return render_template(
            "pages/logs.html", logs=[], pagination=pagination, start_page=start_page, end_page=end_page, args=args
        )

    query = {"bool": {"must": filters}}

    logs, total = es_search_paginated(
        index="winlog-*",
        query=query,
        page_size=per_page,
        page=page
    )

    _, pagination, start_page, end_page, args = paginate(logs, page=page, per_page=per_page, total=total)

    return render_template(
        "pages/logs.html",
        logs=logs,
        pagination=pagination,
        start_page=start_page,
        end_page=end_page,
        args=args
    )


def create_anomaly_from_log():
    """
    Cria anomalia a partir de log selecionado (POST JSON: {index, id})
    """
    data = request.get_json(force=True)
    index = data.get("index")
    doc_id = data.get("id")

    if not index or not doc_id:
        return jsonify({"error": "Faltam parâmetros index/id"}), 400

    try:
        doc = es.get(index=index, id=doc_id)
        src = doc.get("_source", {})

        event_code = (src.get("event") or {}).get("code")
        provider = (src.get("winlog") or {}).get("provider_name")
        message = (src.get("message") or "")
        severity = (src.get("severity") or "low")

        description = f"[ES:{index}/{doc_id}] {provider or '-'} | event={event_code or '-'} | {message}"
        anomaly = Anomaly(
            source=current_user.username,
            description=description,
            severity=severity,
            log_id=doc_id,
        )
        db.session.add(anomaly)
        db.session.commit()  # ensure anomaly.id exists

        # Link anomaly to most relevant policy chunk(s)
        try:
            link_anomaly_to_policy_chunks(anomaly, top_k=1)
        except Exception as _e:
            # Non-fatal
            print(f"[WARN] Could not link anomaly to policy chunks: {_e}")

        flash("Anomalia criada manualmente a partir de log do ES.", "Sucesso")
        return jsonify({"ok": True, "log": src})
    except Exception as e:
        print(f"Erro ao criar anomalia a partir do log ES: {e}")
        flash(f"Erro ao criar anomalia", "Erro")
        return jsonify({"error": str(e)}), 500
