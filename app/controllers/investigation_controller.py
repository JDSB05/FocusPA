from flask import jsonify, request, render_template, send_file, redirect, url_for
from io import BytesIO
from flask_login import current_user
from ..model import Anomaly, Investigation, File, db, Note
from ..utils.pagination import paginate

def investigation_dropdown():
    investigations = Investigation.query.filter_by(state='open').all()
    return jsonify([{'id': i.id, 'title': i.title} for i in investigations])

def start_investigation(anomaly_id):
    # Obter a anomalia
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    
    # Criar a investigação associada à anomalia
    inv = Investigation(
        title=f"Investigação {anomaly.id}",
        description=anomaly.description,
        responsible_id=current_user.id
    )
    # Associar a anomalia à investigação, se tiver relação Many-to-Many
    inv.anomalies.append(anomaly)
    
    db.session.add(inv)
    db.session.commit()
    
    return jsonify({"message": "Investigação criada", "investigation_id": inv.id}), 201

def complete_investigation(id):
    investigation = Investigation.query.get_or_404(id)

    if investigation.state == "closed":
        return jsonify({"message": "Investigação já se encontra concluída"}), 400

    investigation.state = "closed"
    db.session.commit()

    return jsonify({"message": "Investigação concluída com sucesso"})

def list_investigations():
    """Lista investigações utilizando paginação reutilizável."""

    items, pagination, start_page, end_page = paginate(
        Investigation.query.order_by(Investigation.created_at.desc()), per_page=20
    )

    return render_template(
        'pages/investigations.html',
        investigations=items,
        pagination=pagination,
        start_page=start_page,
        end_page=end_page
    )

def investigation_detail(id):
    investigation = Investigation.query.get_or_404(id)
    return render_template("pages/investigation_detail.html", investigation=investigation)

def add_anomaly(inv_id, anomaly_id):
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    investigation = Investigation.query.get_or_404(inv_id)

    if anomaly and investigation:
        investigation.anomalies.append(anomaly)  # assumindo relacionamento many-to-many
        db.session.commit()
        return '', 204
    return 'Anomalia ou Investigação não encontrada', 404

def remove_anomaly(inv_id, anomaly_id):
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    investigation = Investigation.query.get_or_404(inv_id)
    if anomaly in investigation.anomalies:
        investigation.anomalies.remove(anomaly)
        db.session.commit()
    return redirect(url_for('investigation.detail', id=inv_id))

def upload_file(inv_id):
    f = request.files['file']
    file = File(
        investigation_id=inv_id,
        filename=f.filename,
        data=f.read(),
        mimetype=f.mimetype
    )
    db.session.add(file)
    db.session.commit()
    return redirect(url_for('investigation.detail', id=inv_id))

def delete_file(inv_id, file_id):
    file = File.query.get_or_404(file_id)
    db.session.delete(file)
    db.session.commit()
    return redirect(url_for('investigation.detail', id=inv_id))

def download_file(inv_id, file_id):
    file = File.query.get_or_404(file_id)
    return send_file(
        BytesIO(file.data),
        mimetype=file.mimetype or "application/octet-stream",
        as_attachment=True,
        download_name=file.filename
    )

def add_note(inv_id):
    content = request.form.get("content")  # lê o campo 'content' do formulário
    if content:
        note = Note(content=content, investigation_id=inv_id)
        db.session.add(note)
        db.session.commit()
    return redirect(url_for('investigation.detail', id=inv_id))

def delete_note(inv_id, note_id):
    note = Note.query.get_or_404(note_id)
    db.session.delete(note)
    db.session.commit()
    return redirect(url_for('investigation.detail', id=inv_id))