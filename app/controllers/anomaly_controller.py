from flask import render_template, request, jsonify

from ..extensions import db
from ..model import Anomaly


def list_anomalies():
    registros = Anomaly.query.order_by(Anomaly.timestamp.desc()).all()
    return render_template('pages/anomalies.html', anomalies=registros)


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
