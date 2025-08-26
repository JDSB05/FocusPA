from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user

from app.utils.others import get_client_ip

from ..extensions import db
from ..model import User, AccessLog


def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            log = AccessLog(user_id=user.id, action='login', ip_address=get_client_ip(), meta_info={"user_agent": request.user_agent.string})
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('main.dashboard'))
        flash('Credenciais inválidas.', 'Erro')
    return render_template('pages/login.html')


def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if not username or not email or not password:
            flash("Todos os campos são obrigatórios.", 'Erro')
        if User.query.filter((User.username == username) | (User.email == email)).first():  # type: ignore
            flash('Utilizador já existe.', 'Erro')
        else:
            user = User(username=username, email=email)  # type: ignore
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Registo concluído. Faça login.', 'Sucesso')
            return redirect(url_for('auth.login'))
    return render_template('pages/register.html')


def logout():
    log = AccessLog(user_id=current_user.id, action='logout', ip_address=get_client_ip(), meta_info={"user_agent": request.user_agent.string})  
    db.session.add(log)
    db.session.commit()
    logout_user()
    flash('Saiu com sucesso.', 'Sucesso')
    return redirect(url_for('auth.login'))
