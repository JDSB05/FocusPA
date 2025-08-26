from flask import render_template, request, jsonify, flash
import flask

from ..extensions import db
from ..model import Anomaly, Investigation


def list_anomalies():
    page = request.args.get('page', 1, type=int)
    per_page = 20  # nº de registos por página

    # Filtro por campo booleano "investigacao" (true/false)
    investigacao_param = request.args.get('investigacao')
    investigacao_filter = None
    if investigacao_param is not None:
        val = investigacao_param.strip().lower()
        if val in {'1', 'true', 't', 'yes', 'y', 'on'}:
            investigacao_filter = True
        elif val in {'0', 'false', 'f', 'no', 'n', 'off'}:
            investigacao_filter = False

    query = Anomaly.query
    if investigacao_filter is not None:
        exists_q = Anomaly.investigations.any()
        if investigacao_filter:
            query = query.filter(exists_q)
        else:
            query = query.filter(~exists_q)

    pagination = query.order_by(Anomaly.timestamp.desc()) \
                      .paginate(page=page, per_page=per_page, error_out=False)

    # Garante que cada anomalia tem o atributo .investigacao como True/False
    anomalies = []
    for a in pagination.items:
        a.investigacao = bool(a.investigations)   # True se tiver investigações, False se não
        anomalies.append(a)

    start_page = max(1, pagination.page - 2)
    end_page   = min(pagination.pages, pagination.page + 2)

    return render_template(
        'pages/anomalies.html',
        anomalies=anomalies,
        pagination=pagination,
        start_page=start_page,
        end_page=end_page,
        investigacao=investigacao_filter
    )

def get_anomaly(anomaly_id: int):
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    return jsonify({
        'id': anomaly.id,
        'timestamp': anomaly.timestamp.isoformat(),
        'source': anomaly.source,
        'description': anomaly.description,
        'severity': anomaly.severity,
        'resolved': anomaly.resolved,
        'resolved_at': anomaly.resolved_at.isoformat() if anomaly.resolved_at else None,
        'investigacao': getattr(anomaly, 'investigacao', None),
    })


def create_anomaly():
    data = request.get_json() or {}
    anomaly = Anomaly(
        source=data.get('source'),  # type: ignore
        description=data.get('description'),  # type: ignore
        severity=data.get('severity', 'low'),  # type: ignore
    )
    db.session.add(anomaly)
    db.session.commit()
    return jsonify({'id': anomaly.id}), 201


def update_anomaly(anomaly_id: int):
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    data = request.get_json() or {}
    for attr in ['source', 'description', 'severity']:
        if attr in data:
            setattr(anomaly, attr, data[attr])
    if data.get('resolved'):
        anomaly.mark_resolved()
    db.session.commit()
    return jsonify({'message': 'updated'})


def delete_anomaly(anomaly_id: int):
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    db.session.delete(anomaly)
    db.session.commit()
    return jsonify({'message': 'deleted'})

def resolve_anomaly(anomaly_id: int):
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    if anomaly.resolved:
        flash("Anomalia já resolvida, não é possível resolver novamente", "Erro")
        return jsonify({'message': 'anomaly already resolved'}), 400
    anomaly.mark_resolved()
    db.session.commit()
    return jsonify({'message': 'resolved'})