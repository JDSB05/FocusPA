from datetime import datetime
from flask import render_template, request, jsonify

from ..services.elastic import es


def dashboard():
    return render_template('pages/dashboard.html')


def access_control():
    return render_template('pages/access_control.html')


def forensic():
    return render_template('pages/forensic.html')


def compliance():
    return render_template('pages/compliance.html')


def receber_log():
    log = request.get_json()
    if log is None:
        return jsonify({'error': 'Invalid or missing JSON in request'}), 400
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
