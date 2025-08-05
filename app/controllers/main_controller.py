from datetime import datetime, timedelta
from flask import render_template, request, jsonify
from ..extensions import db
from ..model import Anomaly, AccessLog
from sqlalchemy.orm import joinedload


from ..services.elastic import es


def dashboard():
    # 1. Total de anomalias
    total = Anomaly.query.count()

    # 2. Quantas já estão resolvidas
    resolved_count = Anomaly.query.filter_by(resolved=True).count()

    # 3. Taxa de conformidade em percentagem
    compliance_rate = round((resolved_count / total) * 100, 2) if total else 0

    # 4. Preparar dados do gráfico: contagem diária dos últimos 14 dias
    end = datetime.utcnow().date()
    start = end - timedelta(days=13)
    labels = []
    data   = []
    for i in range(14):
        dia = start + timedelta(days=i)
        conta = Anomaly.query.filter(
            db.func.date(Anomaly.timestamp) == dia
        ).count()
        labels.append(dia.isoformat())
        data.append(conta)

    return render_template(
        'pages/dashboard.html',
        total_anomalies=total,
        compliance_rate=compliance_rate,
        chart_labels=labels,
        chart_data=data
    )

def access_control():
    logs = (AccessLog.query
            .options(joinedload(AccessLog.user)) # type: ignore
            .order_by(AccessLog.timestamp.desc())
            .limit(200)  # limita para não carregar tudo
            .all())
    return render_template('pages/access_control.html', logs=logs)



def forensic():
    return render_template('pages/forensic.html')


def compliance():
    return render_template('pages/compliance.html')

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
