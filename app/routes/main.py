from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from ..extensions import db
from ..model import Policy, Anomaly
from ..services.elastic import es
from ..services.chroma import collection
import uuid


main_bp = Blueprint('main', __name__)


@main_bp.route('/', endpoint='dashboard')
@login_required
def dashboard():
    return render_template('pages/dashboard.html')


@main_bp.route('/anomalies', endpoint='anomalies')
@login_required
def anomalies():
    registros = Anomaly.query.order_by(Anomaly.timestamp.desc()).all()
    return render_template('pages/anomalies.html', anomalies=registros)


@main_bp.route('/policies', endpoint='policies')
@login_required
def policies():
    return render_template('pages/policies.html')


@main_bp.route('/policies/upload', methods=['POST'], endpoint='policy_upload')
@login_required
def policy_upload():
    arquivo = request.files.get('file')
    if not arquivo:
        flash('Nenhum ficheiro enviado.')
        return redirect(url_for('main.policies'))

    texto = arquivo.read().decode('utf-8', errors='ignore')
    collection.add(documents=[texto], ids=[str(uuid.uuid4())])
    flash('Política carregada para a ChromaDB.')
    return redirect(url_for('main.policies'))


@main_bp.route('/access-control', endpoint='access_control')
@login_required
def access_control():
    return render_template('pages/access_control.html')


@main_bp.route('/forensic', endpoint='forensic')
@login_required
def forensic():
    return render_template('pages/forensic.html')


@main_bp.route('/compliance', endpoint='compliance')
@login_required
def compliance():
    return render_template('pages/compliance.html')


@main_bp.route('/logs', methods=['POST'], endpoint='logs')
@login_required
def receber_log():
    log = request.get_json()
    if log is None:
        return jsonify({'error': 'Invalid or missing JSON in request'}), 400
    log['timestamp'] = datetime.utcnow().isoformat()
    res = es.index(index='logs_security', document=log)
    return jsonify(res['result'])


@main_bp.route('/search', endpoint='search')
@login_required
def procurar_logs():
    termo = request.args.get('q', '')
    res = es.search(index='logs_security', body={
        'query': {'match': {'message': termo}},
        'size': 10
    })
    hits = [hit['_source'] for hit in res['hits']['hits']]
    return jsonify(hits)
