from datetime import datetime, timedelta
from typing import Counter
from flask import render_template, request, jsonify, get_flashed_messages
from ..extensions import db
from ..model import Anomaly, AccessLog, Policy, AnomalyPolicyLink
from sqlalchemy.orm import joinedload


from ..services.elastic import es


def dashboard():
    total = Anomaly.query.count()
    resolved_count = Anomaly.query.filter_by(resolved=True).count()
    compliance_rate = round((resolved_count / total) * 100, 2) if total else 0

    # Gráfico de linhas (últimos 14 dias)
    end = datetime.utcnow().date()
    start = end - timedelta(days=13)
    labels, data = [], []
    for i in range(14):
        dia = start + timedelta(days=i)
        count = Anomaly.query.filter(db.func.date(Anomaly.timestamp) == dia).count()
        labels.append(dia.isoformat())
        data.append(count)

    # Contagem por severidade
    severities = ['low','medium','high']
    severity_counts = {s: Anomaly.query.filter_by(severity=s).count() for s in severities}

    # Contagem resolvidas vs pendentes
    status_counts = {
        'Resolvidas': resolved_count,
        'Pendentes': total - resolved_count
    }

    # Top 5 anomalias mais recentes
    top_anomalies = (Anomaly.query.order_by(Anomaly.timestamp.desc())
                     .limit(5)
                     .all())

    return render_template(
        'pages/dashboard.html',
        total_anomalies=total,
        compliance_rate=compliance_rate,
        chart_labels=labels,
        chart_data=data,
        severity_counts=severity_counts,
        status_counts=status_counts,
        top_anomalies=top_anomalies
    )

def access_control():
    logs = (AccessLog.query
            .options(joinedload(AccessLog.user))  # type: ignore
            .order_by(AccessLog.timestamp.desc())
            .limit(200)
            .all())

    # Contagem de ações
    action_counts = Counter([log.action for log in logs])

    # Acessos diários (últimos 7 dias)
    today  = datetime.utcnow().date()
    dates  = [today - timedelta(days=i) for i in range(6, -1, -1)]
    daily_counts = []
    daily_labels = [d.strftime('%Y-%m-%d') for d in dates]
    for d in dates:
        count = AccessLog.query.filter(db.func.date(AccessLog.timestamp) == d).count()
        daily_counts.append(count)

    return render_template('pages/access_control.html',
                           logs=logs,
                           action_counts=action_counts,
                           daily_labels=daily_labels,
                           daily_counts=daily_counts)

def compliance():
    policies = Policy.query.order_by(Policy.name).all()

    # Compute per-policy totals using links
    per_policy = []
    for p in policies:
        # All anomalies linked to this policy
        total = (db.session.query(Anomaly)
                 .join(AnomalyPolicyLink, AnomalyPolicyLink.anomaly_id == Anomaly.id)
                 .filter(AnomalyPolicyLink.policy_name == p.name)
                 .count())

        resolved = (db.session.query(Anomaly)
                    .join(AnomalyPolicyLink, AnomalyPolicyLink.anomaly_id == Anomaly.id)
                    .filter(AnomalyPolicyLink.policy_name == p.name, Anomaly.resolved.is_(True))
                    .count())

        rate = round((resolved / total) * 100, 2) if total else 100.0
        per_policy.append({
            'policy': p,
            'total': total,
            'resolved': resolved,
            'rate': rate,
        })

    # Global rate on linked anomalies (fallback to all anomalies if none linked yet)
    linked_total = db.session.query(AnomalyPolicyLink).count()
    if linked_total:
        total_anoms = (db.session.query(Anomaly)
                       .join(AnomalyPolicyLink, AnomalyPolicyLink.anomaly_id == Anomaly.id)
                       .count())
        resolved_anoms = (db.session.query(Anomaly)
                          .join(AnomalyPolicyLink, AnomalyPolicyLink.anomaly_id == Anomaly.id)
                          .filter(Anomaly.resolved.is_(True))
                          .count())
    else:
        total_anoms = Anomaly.query.count()
        resolved_anoms = Anomaly.query.filter_by(resolved=True).count()

    global_rate = round((resolved_anoms / total_anoms) * 100, 2) if total_anoms else 0

    return render_template('pages/compliance.html',
                           per_policy=per_policy,
                           global_rate=global_rate)


def flashes_json():
    """Return and clear Flask flashed messages as JSON list of [category, message]."""
    msgs = get_flashed_messages(with_categories=True)
    return jsonify(msgs)

def chat():
    return render_template('pages/chat.html')


def receber_log():
    log = request.get_json()
    if log is None:
        return jsonify({'Erro': 'Invalid or missing JSON in request'}), 400
    log['timestamp'] = datetime.now().isoformat()
    res = es.index(index='logs_security', document=log)
    return jsonify(res['result'])


def procurar_logs():
    termo = request.args.get('q', '')
    res = es.search(index='logs_security', body={
        'query': {'match': {'message': termo}},
        'size': 10
    })
    hits = [hit['_source'] for hit in res['hits']['hits']]
    return jsonify(hits)
