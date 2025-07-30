from pydoc import doc
from flask import render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename

from ..extensions import db
from ..model import Policy
from ..utils.text_extractor import extract_text_from_file

import os

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.schema import Document

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Setup Chroma
embedding_function = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
chroma = Chroma(persist_directory="chroma_db", embedding_function=embedding_function)


def list_policies():
    todas = Policy.query.order_by(Policy.name).all()
    return render_template('pages/policies.html', policies=todas)

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
        except Exception as e:
            flash(f"Erro ao extrair texto: {e}", 'Erro')
            return redirect(request.url)

        # PostgreSQL
        policy = Policy(name=name, content=content) # type: ignore
        db.session.add(policy)
        db.session.commit()

        # Chroma
        doc = Document(page_content=content, metadata={"source": name})
        chroma.add_documents([doc])
        print("Coleções disponíveis:", chroma._collection.name)
        print("Número de documentos:", chroma._collection.count())
        docs = chroma._collection.get()
        print(docs['documents'])  # Conteúdo dos documentos
        print(docs['metadatas'])  # Metadados associados (ex: nome da policy)



        flash('Política criada com sucesso.', 'Sucesso')
        return redirect(url_for('policy.list_policies'))

    return render_template('pages/policy_form.html')

def policy_edit(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)
    old_name = policy.name  # ← Guarda o nome antigo

    if request.method == 'POST':
        new_name = request.form.get('name')
        policy.name = new_name  # ← Aplica o novo nome

        file = request.files.get('file')
        if file and file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)

            try:
                content = extract_text_from_file(filepath)
                policy.content = content

                # Apaga os documentos anteriores no Chroma
                matching_docs = chroma._collection.get(where={"source": old_name})
                ids_to_delete = matching_docs.get("ids", [])
                if ids_to_delete:
                    chroma._collection.delete(ids=ids_to_delete)

                # Insere com o novo nome
                doc = Document(page_content=content, metadata={"source": new_name})
                chroma.add_documents([doc])
                docs = chroma._collection.get()
                print(docs['documents'])  # Conteúdo dos documentos
                print(docs['metadatas'])  # Metadados associados (ex: nome da policy)

            except Exception as e:
                flash(f"Erro ao extrair texto: {e}", 'Erro')
                return redirect(request.url)
        else:
            # Só o nome mudou → atualiza metadados na Chroma
            if new_name != old_name:
                try:
                    matching_docs = chroma._collection.get(where={"source": old_name})
                    ids_to_delete = matching_docs.get("ids", [])
                    if ids_to_delete:
                        chroma._collection.delete(ids=ids_to_delete)

                        # Reinsere com novo nome, mesmo conteúdo
                        doc = Document(page_content=policy.content, metadata={"source": new_name})
                        chroma.add_documents([doc])
                        docs = chroma._collection.get()
                        print(docs['documents'])  # Conteúdo dos documentos
                        print(docs['metadatas'])  # Metadados associados (ex: nome da policy)

                except Exception as e:
                    flash(f"Erro ao atualizar Chroma: {e}", 'Erro')
                    return redirect(request.url)

        db.session.commit()
        flash('Política atualizada.', 'Sucesso')
        return redirect(url_for('policy.list_policies'))

    return render_template('pages/policy_form.html', policy=policy)

def policy_delete(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)

    try:
        # 1. Apaga da Chroma pelo "source" (nome da política)
        matching_docs = chroma._collection.get(where={"source": policy.name})
        ids_to_delete = matching_docs.get("ids", [])
        if ids_to_delete:
            chroma._collection.delete(ids=ids_to_delete)
            docs = chroma._collection.get()
            print(docs['documents'])  # Conteúdo dos documentos
            print(docs['metadatas'])  # Metadados associados (ex: nome da policy)

    except Exception as e:
        flash(f"Erro ao apagar no Chroma: {e}", 'Erro')

    # 2. Apaga da base de dados PostgreSQL
    db.session.delete(policy)
    db.session.commit()
    flash('Política removida.', 'Sucesso')
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
    return jsonify({'result': 'Policy uploaded Sucessofully'}), 201
