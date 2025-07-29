from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from elasticsearch import Elasticsearch

main_bp = Blueprint('main', __name__)

# Ligação ao Elasticsearch
es = Elasticsearch("http://localhost:9200")

@main_bp.route('/')
def dashboard():
    return render_template('pages/dashboard.html')

@main_bp.route('/anomalies')
def anomalies():
    return render_template('pages/anomalies.html')

@main_bp.route('/policies')
def policies():
    return render_template('pages/policies.html')

@main_bp.route('/access-control')
def access_control():
    return render_template('pages/access_control.html')

@main_bp.route('/forensic')
def forensic():
    return render_template('pages/forensic.html')

@main_bp.route('/compliance')
def compliance():
    return render_template('pages/compliance.html')

@main_bp.route('/logout')
def logout():
    flash('Saiu com sucesso.')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/logs', methods=['POST'])
def receber_log():
    log = request.get_json()
    if log is None:
        return jsonify({'error': 'Invalid or missing JSON in request'}), 400
    log['timestamp'] = datetime.utcnow().isoformat()
    res = es.index(index='logs_security', document=log)
    return jsonify(res['result'])

@main_bp.route('/search')
def procurar_logs():
    termo = request.args.get('q', '')
    res = es.search(index='logs_security', body={
        'query': {'match': {'message': termo}},
        'size': 10
    })
    hits = [hit['_source'] for hit in res['hits']['hits']]
    return jsonify(hits)
