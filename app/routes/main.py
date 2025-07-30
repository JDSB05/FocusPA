from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from ..extensions import db
from ..model import Policy, Anomaly
from ..services.elastic import es


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
    todas = Policy.query.order_by(Policy.name).all()
    return render_template('pages/policies.html', policies=todas)


@main_bp.route('/policies/new', methods=['GET', 'POST'], endpoint='policy_new')
@login_required
def policy_new():
    if request.method == 'POST':
        policy = Policy(
            name=request.form.get('name'),  # type: ignore
            description=request.form.get('description'), # type: ignore
            content=request.form.get('content') # type: ignore
        )
        db.session.add(policy)
        db.session.commit()
        flash('Política criada.')
        return redirect(url_for('policies'))
    return render_template('pages/policy_form.html')


@main_bp.route('/policies/<int:policy_id>/edit', methods=['GET', 'POST'], endpoint='policy_edit')
@login_required
def policy_edit(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)
    if request.method == 'POST':
        policy.name = request.form.get('name')
        policy.description = request.form.get('description')
        policy.content = request.form.get('content')
        db.session.commit()
        flash('Política atualizada.')
        return redirect(url_for('policies'))
    return render_template('pages/policy_form.html', policy=policy)


@main_bp.route('/policies/<int:policy_id>/delete', methods=['POST'], endpoint='policy_delete')
@login_required
def policy_delete(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)
    db.session.delete(policy)
    db.session.commit()
    flash('Política removida.')
    return redirect(url_for('policies'))


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
    log['timestamp'] = datetime.now().isoformat()
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

@main_bp.route('/uploadpolicy', methods=['POST'], endpoint='upload_policy')
@login_required
def upload_policy():
    policy_data = request.get_json()
    if not policy_data:
        return jsonify({'error': 'Invalid or missing JSON in request'}), 400
    policy = Policy(
        name=policy_data.get('name'), # type: ignore
        description=policy_data.get('description'), # type: ignore
        content=policy_data.get('content') # type: ignore
    )
    db.session.add(policy)
    db.session.commit()
    return jsonify({'result': 'Policy uploaded successfully'}), 201