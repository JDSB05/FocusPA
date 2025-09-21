from flask import render_template, request, redirect, url_for, flash, jsonify
from sympy import content
from werkzeug.utils import secure_filename
import os

from ..extensions import db
from ..model import Policy
from ..utils.text_extractor import extract_text_from_file
from ..services.chroma_client import chroma

from datetime import datetime
import mimetypes

from ..utils.text_chunker import get_embedding_chunks, get_h_questions, nat_lang_to_es, split_into_word_chunks
from ..services.embeddings import embed

USE_HYDE = os.getenv("USE_HYDE", "false").lower() == "true"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def list_policies():
    """Retorna todas as políticas armazenadas."""
    return render_template('pages/policies.html', policies=Policy.query.order_by(Policy.name).all(), items={'documents': [], 'ids': [], 'metadatas': {'es_query': [], 'reasoning': []}})

def add_policy(name: str, content: str, base_meta: dict | None = None):
    """
    Adiciona uma política à Chroma (em chunks) e à BD.
    - Chroma: múltiplos documentos (1 por chunk) com embeddings e metadados.
    - BD: guarda o texto completo como já fazias.
    """
    col = chroma.get_or_create_collection("policies")

    # 1) Chunking
    chunks = split_into_word_chunks(content, chunk_words=800, overlap=80)
    total = len(chunks) if chunks else 1
    if not chunks:
        chunks = [content]

    h_questions = get_h_questions(chunks) if USE_HYDE else []
    
    llm_data = [nat_lang_to_es(c) for c in chunks]
    chunk_es_queries, chunk_reasonings = zip(*llm_data) if llm_data else ([], [])
    chunk_es_queries = list(chunk_es_queries)
    chunk_reasonings = list(chunk_reasonings)

    # 2) Embeddings (um por chunk)
    # embeddings = embed(chunks)
    embeddings = embed(get_embedding_chunks(name, base_meta.get("filename", "unknown") if base_meta else "unknown", chunks, h_questions))    

    # 3) IDs estáveis por chunk (evita conflitos)
    ids = [f"{name}::chunk-{i:04d}" for i in range(total)]

    # 4) Metadados por chunk
    base_meta = base_meta or {}
    metadatas = []
    for i in range(total):
        md = {
            "name": name,
            "chunk_index": i,
            "total_chunks": total,
            "ingested_at": datetime.utcnow().isoformat() + "Z",
            "es_query": chunk_es_queries[i] if i < len(chunk_es_queries) else None,
            "reasoning": chunk_reasonings[i] if i < len(chunk_reasonings) else None,
        }
        md.update(base_meta)
        metadatas.append(md)

    col.add(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
    print("[INFO] [Chroma] Policy chunks added")

    # 6) BD (mantém igual – texto completo)
    policy = Policy(name=name, content=content)  # type: ignore
    db.session.add(policy)
    db.session.commit()

    return ids


def save_signatures():
    if request.method == 'POST':
        data = request.get_json()
        if not data or 'accepted' not in data or 'rejected' not in data:
            return jsonify({'error': 'Invalid or missing data'}), 400

        accepted = data['accepted']
        rejected = data['rejected']

        # Update ChromaDB: set es_query and reasoning to "" for rejected chunks
        col = chroma.get_or_create_collection("policies")
        for chunk_id in rejected:
            try:
                # Update only the rejected chunk's metadata
                col.update(
                    ids=[chunk_id],
                    metadatas=[{"es_query": "", "reasoning": ""}]
                )
            except Exception as e:
                print(f"[ERROR] [save_signatures] Failed to clear metadata for {chunk_id}: {e}")

        return jsonify({'accepted': accepted}), 200


def review_extracted_signs(ids: list[str]):
    """ Prepara o HTML para rever as assinaturas (queries ES dos eventos que não respeitam a politica correspondente) extraídas automáticamente pelo LLM.
    Também prepara as razões (reasoning) para cada query. """

    col = chroma.get_or_create_collection("policies")
    res = col.get(ids=ids, include=["documents", "metadatas"])

    # Filtra as entradas sem es_query (queries vazias)
    filtered_indexes = [
        i for i, md in enumerate(res.get('metadatas', []))
        if md.get('es_query', '') != ""
    ]

    # Reconstrói o dicionário com os itens filtrados
    items = {
        'documents': [res['documents'][i] for i in filtered_indexes],
        'ids': [res['ids'][i] for i in filtered_indexes],
        'metadatas': {
            'es_query': [res['metadatas'][i].get('es_query', '') for i in filtered_indexes],
            'reasoning': [res['metadatas'][i].get('reasoning', '') for i in filtered_indexes]
        }
    }

    return render_template('pages/policies.html', items=items)

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
            # Extrai texto do ficheiro
            content = extract_text_from_file(filepath)

            if not content or not content.strip():
                flash("O ficheiro não contém texto extraível.", "Erro")
                return redirect(request.url)

            # Normalizar whitespace antes de chunking (melhora embeddings)
            content = " ".join(content.split())

            # Metadados do ficheiro para guardar na Chroma por chunk
            stat = os.stat(filepath)
            base_meta = {
                "filename": filename,
                "file_ext": os.path.splitext(filename)[1].lower(),
                "filesize": stat.st_size,
                "file_mtime": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                "mimetype": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            }

            # Garante que não há duplicados na Chroma (apaga por metadata name=<name>)
            print(f"[DEBUG] [Chroma] Apagando a política {name}, para garantir que não há duplicados.")
            delete_policy(name)

            # Adiciona em chunks com metadados e embeddings
            added_ids = add_policy(name=name, content=content, base_meta=base_meta)

            flash('Política criada com sucesso.', 'Sucesso')
            return review_extracted_signs(added_ids)
            # return render_template('pages/policies_.html')
        
        except Exception as e:
            import traceback
            print(f"Erro ao processar política: {type(e).__name__}: {e}")
            traceback.print_exc()
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

                if not content or not content.strip():
                    flash("O ficheiro não contém texto extraível.", "Erro")
                    return redirect(request.url)

                stat = os.stat(filepath)
                base_meta = {
                    "filename": filename,
                    "file_ext": os.path.splitext(filename)[1].lower(),
                    "filesize": stat.st_size,
                    "file_mtime": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                    "mimetype": mimetypes.guess_type(filename)[0] or "application/octet-stream",
                }

                delete_policy(old_name)
                add_policy(name=new_name, content=content, base_meta=base_meta)  # type: ignore
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

def delete_policy(name: str) -> int:
    """Remove todos os chunks da política no Chroma e a entrada na BD. Devolve nº de chunks apagados."""
    col = chroma.get_or_create_collection("policies")
    print(f"[INFO] [Chroma] Deleting policy '{name}' (by metadata)")

    deleted_count = 0
    try:
        # Pede só metadados para não puxar embeddings/documentos pesados; 'ids' vem sempre no resultado
        res = col.get(where={"name": name}, include=["metadatas"])
        ids = (res.get("ids") or [])
        deleted_count = len(ids)
    except Exception as e:
        print(f"[WARN] [Chroma] Não foi possível contar chunks antes de apagar: {e}")

    try:
        col.delete(where={"name": name})
        print(f"[INFO] [Chroma] Policy deleted from ChromaDB ({deleted_count} chunks).")
    except Exception as e:
        print(f"[ERROR] [Chroma] Erro ao apagar na Chroma: {e}")

    # Apaga da BD
    policy = Policy.query.filter_by(name=name).first()
    if policy:
        db.session.delete(policy)
        db.session.commit()

    return deleted_count

def policy_delete(policy_id: int):
    policy = Policy.query.get_or_404(policy_id)
    try:
        n = delete_policy(policy.name)
        unidade = "chunk" if n == 1 else "chunks"
        flash(f'Política removida. {n} {unidade} apagado(s) na Chroma.', 'Sucesso')
    except Exception as e:
        flash(f"Erro ao apagar política: {e}", 'Erro')
    return redirect(url_for('policy.list_policies'))

def upload_policy():
    if request.content_type.startswith('multipart/form-data'):
        file = request.files.get('file')
        name = request.form.get('name')
        print(f"[DEBUG] [Chroma] Uploading policy: name={name}, file={file}")

        if not file or not name or file.filename is None:
            flash('Nome e ficheiro são obrigatórios', 'Erro')
            return jsonify({'error': 'Nome e ficheiro são obrigatórios'}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        try:
            content = extract_text_from_file(filepath)

            if not content or not content.strip():
                flash('O ficheiro não contém texto extraível.', 'Erro')
                return jsonify({'error': 'O ficheiro não contém texto extraível.'}), 400

            stat = os.stat(filepath)
            base_meta = {
                "filename": filename,
                "file_ext": os.path.splitext(filename)[1].lower(),
                "filesize": stat.st_size,
                "file_mtime": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                "mimetype": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            }

            delete_policy(name)
            add_policy(name=name, content=content, base_meta=base_meta)
            flash('Política carregada com sucesso (ficheiro)', 'Sucesso')
            return jsonify({'result': 'Policy uploaded successfully via file'}), 201
        except Exception as e:
            flash(f'Erro ao processar ficheiro: {e}', 'Erro')
            return jsonify({'error': f'Failed to process file: {e}'}), 500
    else:
        policy_data = request.get_json()
        if not policy_data:
            flash('JSON inválido ou em falta', 'Erro')
            return jsonify({'error': 'Invalid or missing JSON in request'}), 400

        name = policy_data.get('name')
        content = policy_data.get('content')

        try:
            if not content or not str(content).strip():
                flash('Conteúdo vazio.', 'Erro')
                return jsonify({'error': 'Conteúdo vazio.'}), 400

            delete_policy(name)
            add_policy(name=name, content=content)
            flash('Política carregada com sucesso', 'Sucesso')
            return jsonify({'result': 'Policy uploaded successfully'}), 201
        except Exception as e:
            flash(f'Erro ao carregar política: {e}', 'Erro')
            return jsonify({'error': f'Failed to upload policy: {e}'}), 500
