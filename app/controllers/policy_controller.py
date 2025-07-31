from flask import render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import os

from ..extensions import db
from ..model import Policy
from ..utils.text_extractor import extract_text_from_file
from ..services.chroma_client import chroma

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def list_policies():
    """Retorna todas as políticas armazenadas."""
    return render_template('pages/policies.html', policies=Policy.query.order_by(Policy.name).all())

def add_policy(name: str, content: str):
    """Adiciona uma nova política ao Chroma e à BD."""
    # Adiciona ao Chroma
    col = chroma.get_or_create_collection("policies")
    print(f"[INFO] [Chroma] Adding policy '{name}' to ChromaDB")
    col.add(documents=[content], metadatas=[{"name": name}], ids=[name])
    print("[INFO] [Chroma] Policy added to ChromaDB")

    # Adiciona à BD
    policy = Policy(name=name, content=content) # type: ignore
    db.session.add(policy)
    db.session.commit()

def delete_policy(name: str):
    """Remove uma política do Chroma e da BD com base no nome."""
    # Apaga do Chroma
    col = chroma.get_or_create_collection("policies")
    print(f"[INFO] [Chroma] Deleting policy '{name}' from ChromaDB")
    col.delete(ids=[name])
    print("[INFO] [Chroma] Policy deleted from ChromaDB")

    # Apaga da BD
    policy = Policy.query.filter_by(name=name).first()
    if policy:
        db.session.delete(policy)
        db.session.commit()

def policy_new():
    if request.method == 'POST':
        file = request.files.get('file')
        name = request.form.get('name')

        if not file or not name or file.filename is None:
            flash("Nome e ficheiro são obrigatórios.", 'Erro')
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        try:
            content = extract_text_from_file(filepath)
            delete_policy(name)  # Garante que não há duplicados
            add_policy(name=name, content=content)
            flash('Política criada com sucesso.', 'Sucesso')
            return redirect(url_for('policy.list_policies'))
        except Exception as e:
            flash(f"Erro ao processar política: {e}", 'Erro')
            return redirect(request.url)

    return render_template('pages/policy_form.html')

def policy_edit(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)
    old_name = policy.name

    if request.method == 'POST':
        new_name = request.form.get('name')
        file = request.files.get('file')

        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            try:
                content = extract_text_from_file(filepath)
                delete_policy(old_name)
                add_policy(name=new_name, content=content) # type: ignore
                flash('Política atualizada.', 'Sucesso')
            except Exception as e:
                flash(f"Erro ao atualizar política: {e}", 'Erro')
                return redirect(request.url)
        else:
            try:
                if new_name != old_name:
                    delete_policy(old_name)
                    add_policy(name=new_name, content=policy.content) # type: ignore
                    flash('Política renomeada com sucesso.', 'Sucesso')
            except Exception as e:
                flash(f"Erro ao renomear política: {e}", 'Erro')
                return redirect(request.url)

        return redirect(url_for('policy.list_policies'))

    return render_template('pages/policy_form.html', policy=policy)

def policy_delete(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)
    try:
        delete_policy(policy.name)
        flash('Política removida.', 'Sucesso')
    except Exception as e:
        flash(f"Erro ao apagar política: {e}", 'Erro')
    return redirect(url_for('policy.list_policies'))

def upload_policy():
    if request.content_type.startswith('multipart/form-data'):
        file = request.files.get('file')
        name = request.form.get('name')
        print(f"[DEBUG] [Chroma] Uploading policy: name={name}, file={file}")

        if not file or not name or file.filename is None:
            return jsonify({'error': 'Nome e ficheiro são obrigatórios'}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        try:
            content = extract_text_from_file(filepath)
            delete_policy(name)
            add_policy(name=name, content=content)
            return jsonify({'result': 'Policy uploaded successfully via file'}), 201
        except Exception as e:
            return jsonify({'error': f'Failed to process file: {e}'}), 500
    else:
        policy_data = request.get_json()
        if not policy_data:
            return jsonify({'error': 'Invalid or missing JSON in request'}), 400

        name = policy_data.get('name')
        content = policy_data.get('content')

        try:
            delete_policy(name)
            add_policy(name=name, content=content)
            return jsonify({'result': 'Policy uploaded successfully'}), 201
        except Exception as e:
            return jsonify({'error': f'Failed to upload policy: {e}'}), 500
