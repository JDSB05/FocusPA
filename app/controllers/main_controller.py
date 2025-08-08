from datetime import datetime, timedelta
from typing import Counter
from flask import render_template, request, jsonify
from ..extensions import db
from ..model import Anomaly, AccessLog, Policy
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



def forensic():
    return render_template('pages/forensic.html')


def compliance():
    total = Anomaly.query.count()
    resolved_count = Anomaly.query.filter_by(resolved=True).count()
    compliance_rate = round((resolved_count / total) * 100, 2) if total else 0

    policies = Policy.query.order_by(Policy.name).all()
    return render_template('pages/compliance.html',
                           policies=policies,
                           compliance_rate=compliance_rate)

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
