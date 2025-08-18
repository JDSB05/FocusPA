from flask import jsonify, request, render_template
from flask_login import current_user
from ..model import Anomaly, Investigation, db

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

def list_investigations():
    page = request.args.get('page', 1, type=int)
    per_page = 20  # nº de registos por página

    pagination = Investigation.query.order_by(Investigation.created_at.desc()) \
                                    .paginate(page=page, per_page=per_page, error_out=False)

    start_page = max(1, pagination.page - 2)
    end_page   = min(pagination.pages, pagination.page + 2)

    return render_template(
        'pages/investigations.html',
        investigations=pagination.items,
        pagination=pagination,
        start_page=start_page,
        end_page=end_page
    )

def investigation_detail(id):
    investigation = Investigation.query.get_or_404(id)
    return render_template("pages/investigation_detail.html", investigation=investigation)