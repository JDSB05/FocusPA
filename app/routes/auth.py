from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from ..extensions import db
from ..model import User, AccessLog


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            log = AccessLog(user_id=user.id, action='login') # type: ignore
            db.session.add(log)
            db.session.commit()
            return redirect(url_for('main.dashboard'))
        flash('Credenciais inválidas.')
    return render_template('pages/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'], endpoint='register')
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Utilizador já existe.')
        else:
            user = User(username=username, email=email) # type: ignore
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Registo concluído. Faça login.')
            return redirect(url_for('auth.login'))
    return render_template('pages/register.html')


@auth_bp.route('/logout', endpoint='logout')
@login_required
def logout():
    log = AccessLog(user_id=current_user.id, action='logout') # type: ignore
    db.session.add(log)
    db.session.commit()
    logout_user()
    flash('Saiu com sucesso.')
    return redirect(url_for('auth.login'))
