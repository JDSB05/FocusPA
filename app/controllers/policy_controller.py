from flask import render_template, request, redirect, url_for, flash, jsonify

from ..extensions import db
from ..model import Policy


def list_policies():
    todas = Policy.query.order_by(Policy.name).all()
    return render_template('pages/policies.html', policies=todas)


def policy_new():
    if request.method == 'POST':
        policy = Policy(
            name=request.form.get('name'),  # type: ignore
            content=request.form.get('content')  # type: ignore
        )
        db.session.add(policy)
        db.session.commit()
        flash('Política criada.')
        return redirect(url_for('policy.list_policies'))
    return render_template('pages/policy_form.html')


def policy_edit(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)
    if request.method == 'POST':
        policy.name = request.form.get('name')
        policy.content = request.form.get('content')
        db.session.commit()
        flash('Política atualizada.')
        return redirect(url_for('policy.list_policies'))
    return render_template('pages/policy_form.html', policy=policy)


def policy_delete(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)
    db.session.delete(policy)
    db.session.commit()
    flash('Política removida.')
    return redirect(url_for('policy.list_policies'))


def upload_policy():
    policy_data = request.get_json()
    if not policy_data:
        return jsonify({'error': 'Invalid or missing JSON in request'}), 400
    policy = Policy(
        name=policy_data.get('name'),  # type: ignore
        content=policy_data.get('content')  # type: ignore
    )
    db.session.add(policy)
    db.session.commit()
    return jsonify({'result': 'Policy uploaded successfully'}), 201
