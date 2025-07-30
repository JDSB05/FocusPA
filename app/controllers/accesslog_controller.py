from flask import jsonify

from ..model import AccessLog


def list_logs():
    logs = AccessLog.query.order_by(AccessLog.timestamp.desc()).all()
    serialized = [
        {
            'id': l.id,
            'user_id': l.user_id,
            'timestamp': l.timestamp.isoformat(),
            'action': l.action,
            'resource': l.resource,
            'ip_address': l.ip_address,
        }
        for l in logs
    ]
    return jsonify(serialized)
