"""
app.py — Portal web para familias gerenciarem telefones das criancas.
"""

from datetime import datetime
import functools
import io
import logging
import random
import secrets
import smtplib
import subprocess
import time
from collections import defaultdict
from email.message import EmailMessage
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, abort, Response
)
import qrcode
import config
import models

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Security: cookies
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

DAY_NAMES = ['Segunda', 'Terca', 'Quarta', 'Quinta', 'Sexta', 'Sabado', 'Domingo']

# Rate limiting: max 5 tentativas de login por IP em 15 minutos
LOGIN_ATTEMPTS = defaultdict(list)  # ip -> [timestamps]
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 900


def check_rate_limit(ip):
    """Retorna True se o IP excedeu o limite de tentativas."""
    now = time.time()
    attempts = LOGIN_ATTEMPTS[ip]
    # Limpar tentativas antigas
    LOGIN_ATTEMPTS[ip] = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
    return len(LOGIN_ATTEMPTS[ip]) >= LOGIN_MAX_ATTEMPTS


def record_failed_login(ip):
    LOGIN_ATTEMPTS[ip].append(time.time())


# --- Database ---

def get_db():
    if 'db' not in g:
        g.db = models.get_db(config.DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# --- Auth helpers ---

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if not session.get('is_admin'):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def get_user_device(device_id):
    """Retorna device se pertence ao usuario logado, senao abort 404."""
    db = get_db()
    device = models.get_device(db, device_id)
    if device is None or device['user_id'] != session['user_id']:
        abort(404)
    return device


# --- CSRF protection ---

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


@app.before_request
def csrf_protect():
    if request.method == 'POST':
        token = session.get('_csrf_token')
        form_token = request.form.get('_csrf_token')
        if not token or not form_token or token != form_token:
            abort(403)


# --- Template filters ---

MONTH_NAMES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
               'jul', 'ago', 'set', 'out', 'nov', 'dez']

@app.template_filter('datahora')
def datahora_filter(value):
    """Formata '2026-03-05 16:20:55' para '5 mar 16:20'."""
    try:
        dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        mes = MONTH_NAMES[dt.month - 1]
        return f'{dt.day} {mes} {dt.hour:02d}:{dt.minute:02d}'
    except (ValueError, TypeError):
        return value


# --- Template context ---

@app.context_processor
def inject_globals():
    return {'day_names': DAY_NAMES, 'csrf_token': generate_csrf_token, 'config': config}


# --- Auth routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr
        if check_rate_limit(ip):
            flash('Muitas tentativas. Aguarde 15 minutos.', 'danger')
            return render_template('login.html')

        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and models.check_password(password, user['password_hash']):
            session.clear()  # previne session fixation
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(url_for('dashboard'))
        record_failed_login(ip)
        flash('Email ou senha incorretos.', 'danger')
    return render_template('login.html')


def send_verification_code(to_email, code):
    """Envia codigo de verificacao de 6 digitos por email."""
    msg = EmailMessage()
    msg['Subject'] = 'Telefone Fixo — Codigo de verificacao'
    msg['From'] = config.SMTP_USER
    msg['To'] = to_email
    msg.set_content(
        f"Seu codigo de verificacao e: {code}\n\n"
        f"Digite este codigo no site para confirmar seu email.\n"
        f"O codigo expira em 10 minutos."
    )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


@app.route('/ativar', methods=['GET', 'POST'])
def activate():
    """Ativacao passo 1: valida dados e envia codigo de verificacao por email."""
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        child_name = request.form.get('child_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        if not code or not email or not password or not child_name:
            flash('Preencha todos os campos.', 'danger')
        elif password != password2:
            flash('As senhas nao conferem.', 'danger')
        elif len(password) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
        else:
            db = get_db()
            device = db.execute(
                "SELECT * FROM devices WHERE registration_code = ? AND user_id IS NULL",
                (code,)
            ).fetchone()
            if device is None:
                flash('Codigo invalido ou aparelho ja ativado.', 'danger')
            else:
                existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
                if existing:
                    flash('Este email ja esta cadastrado. Faca login e vincule o aparelho.', 'danger')
                else:
                    verify_code = f"{random.randint(0, 999999):06d}"
                    try:
                        send_verification_code(email, verify_code)
                    except Exception:
                        logging.exception("Erro ao enviar codigo de verificacao")
                        flash('Erro ao enviar email. Verifique o endereco e tente novamente.', 'danger')
                        return render_template('activate.html')
                    session['pending_activation'] = {
                        'device_code': code,
                        'device_id': device['id'],
                        'email': email,
                        'password_hash': models.hash_password(password),
                        'child_name': child_name,
                        'verify_code': verify_code,
                        'expires': time.time() + 600,
                    }
                    flash(f'Codigo de verificacao enviado para {email}.', 'success')
                    return redirect(url_for('verify_email'))
    return render_template('activate.html')


@app.route('/verificar-email', methods=['GET', 'POST'])
def verify_email():
    """Ativacao passo 2: usuario digita o codigo recebido por email."""
    pending = session.get('pending_activation')
    if not pending:
        flash('Nenhuma ativacao em andamento. Comece novamente.', 'danger')
        return redirect(url_for('activate'))

    if time.time() > pending['expires']:
        session.pop('pending_activation', None)
        flash('Codigo expirado. Comece novamente.', 'danger')
        return redirect(url_for('activate'))

    if request.method == 'POST':
        typed_code = request.form.get('code', '').strip()
        if typed_code == pending['verify_code']:
            db = get_db()
            # Re-verificar que device ainda esta livre
            device = db.execute(
                "SELECT * FROM devices WHERE id = ? AND user_id IS NULL",
                (pending['device_id'],)
            ).fetchone()
            if device is None:
                session.pop('pending_activation', None)
                flash('Este aparelho ja foi ativado por outra pessoa.', 'danger')
                return redirect(url_for('activate'))
            db.execute(
                "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
                (pending['email'], pending['password_hash'], f"Familia de {pending['child_name']}")
            )
            db.commit()
            user = db.execute("SELECT * FROM users WHERE email = ?", (pending['email'],)).fetchone()
            db.execute("UPDATE devices SET user_id = ?, child_name = ? WHERE id = ?",
                       (user['id'], pending['child_name'], device['id']))
            db.commit()
            session.pop('pending_activation', None)
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['is_admin'] = False
            flash(f'Email confirmado! Aparelho {device["extension"]} ({device["child_name"]}) vinculado. Autorize os contatos para liberar ligacoes.', 'success')
            return redirect(url_for('contacts', device_id=device['id']))
        else:
            flash('Codigo incorreto. Tente novamente.', 'danger')

    return render_template('verify_email.html', email=pending['email'])


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/excluir-conta', methods=['GET', 'POST'])
@login_required
def delete_account():
    db = get_db()
    devices = models.get_devices_for_user(db, session['user_id'])

    if request.method == 'POST':
        confirmation = request.form.get('confirmation', '').strip()
        if confirmation != 'EXCLUIR':
            flash('Digite EXCLUIR para confirmar.', 'danger')
            return render_template('delete_account.html', devices=devices)

        asterisk_exts = models.delete_account(db, session['user_id'])

        # Remover todas as extensions do Asterisk (child + parent)
        for ext in asterisk_exts:
            remove_asterisk_extension(ext)

        session.clear()
        flash('Conta excluida com sucesso. Todos os dados foram removidos.', 'success')
        return redirect(url_for('login'))

    return render_template('delete_account.html', devices=devices)


# --- Password reset ---

def send_reset_email(to, token):
    """Envia email com link de reset via Gmail SMTP."""
    link = f"{config.SITE_URL}/resetar-senha/{token}"
    msg = EmailMessage()
    msg['Subject'] = 'Telefone Fixo — Redefinir senha'
    msg['From'] = config.SMTP_USER
    msg['To'] = to
    msg.set_content(
        f"Voce pediu para redefinir sua senha.\n\n"
        f"Clique no link abaixo (valido por 1 hora):\n{link}\n\n"
        f"Se voce nao pediu isso, ignore este email."
    )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


def send_permission_email(to_email, from_child, to_child, token):
    """Envia email pedindo que a familia autorize a ligacao."""
    link = f"{config.SITE_URL}/autorizar/{token}"
    msg = EmailMessage()
    msg['Subject'] = f'Telefone Fixo — {from_child} quer ligar para {to_child}'
    msg['From'] = config.SMTP_USER
    msg['To'] = to_email
    msg.set_content(
        f"O telefone de {from_child} foi autorizado a ligar para {to_child}.\n\n"
        f"Para que a ligacao funcione, voce precisa autorizar de volta.\n\n"
        f"Clique no link abaixo para autorizar (valido por 7 dias):\n{link}\n\n"
        f"Se voce nao quer autorizar, ignore este email."
    )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


@app.route('/esqueci-senha', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        ip = request.remote_addr
        if check_rate_limit(ip):
            flash('Muitas tentativas. Aguarde 15 minutos.', 'danger')
            return render_template('forgot_password.html')

        email = request.form.get('email', '').strip().lower()
        record_failed_login(ip)  # conta toda tentativa para limitar abuso
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            token = models.create_reset_token(db, email)
            try:
                send_reset_email(email, token)
            except Exception:
                logging.exception("Erro ao enviar email de reset para %s", email)
        # Mensagem generica sempre (nao revela se email existe)
        flash('Se o email estiver cadastrado, voce recebera um link para redefinir a senha.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/resetar-senha/<token>', methods=['GET', 'POST'])
def reset_password(token):
    db = get_db()
    email = models.validate_reset_token(db, token)
    if not email:
        flash('Link invalido ou expirado. Peca um novo.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        if not password or len(password) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
        elif password != password2:
            flash('As senhas nao conferem.', 'danger')
        else:
            pw_hash = models.hash_password(password)
            db.execute("UPDATE users SET password_hash = ? WHERE email = ?", (pw_hash, email))
            db.commit()
            models.delete_reset_token(db, token)
            flash('Senha redefinida! Faca login com a nova senha.', 'success')
            return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)


# --- Autorizacao por link (email) ---

@app.route('/autorizar/<token>')
def authorize_by_token(token):
    db = get_db()
    result = models.validate_permission_token(db, token)
    if not result:
        flash('Link invalido ou expirado.', 'danger')
        return redirect(url_for('login'))
    from_device_id, to_device_id = result
    from_device = models.get_device(db, from_device_id)
    to_device = models.get_device(db, to_device_id)
    if not from_device or not to_device:
        flash('Aparelho nao encontrado.', 'danger')
        return redirect(url_for('login'))
    # Adicionar permissao reversa: to_device autoriza from_device
    models.add_permission(db, to_device_id, from_device['extension'])
    models.delete_permission_token(db, token)
    flash(f'{to_device["child_name"]} agora pode ligar para {from_device["child_name"]} (e vice-versa)!', 'success')
    return redirect(url_for('login'))


# --- Dashboard ---

@app.route('/')
@login_required
def dashboard():
    db = get_db()
    devices = models.get_devices_for_user(db, session['user_id'])
    if len(devices) == 1:
        return redirect(url_for('contacts', device_id=devices[0]['id']))
    return render_template('dashboard.html', devices=devices)


# --- Devices ---

@app.route('/devices', methods=['GET', 'POST'])
@login_required
def devices():
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        if not code:
            flash('Digite o codigo de registro.', 'danger')
        else:
            db = get_db()
            device = models.link_device(db, code, session['user_id'])
            if device:
                flash(f'Aparelho {device["extension"]} ({device["child_name"]}) vinculado!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Codigo invalido ou aparelho ja vinculado.', 'danger')
    return render_template('devices.html')


# --- Schedule ---

@app.route('/devices/<int:device_id>/schedule', methods=['GET', 'POST'])
@login_required
def schedule(device_id):
    device = get_user_device(device_id)
    db = get_db()

    if request.method == 'POST':
        try:
            for day in range(7):
                enabled = request.form.get(f'enabled_{day}')
                start_h = request.form.get(f'start_h_{day}', '00')
                start_m = request.form.get(f'start_m_{day}', '00')
                end_h = request.form.get(f'end_h_{day}', '00')
                end_m = request.form.get(f'end_m_{day}', '00')
                if enabled:
                    start = f'{start_h}:{start_m}'
                    end = f'{end_h}:{end_m}'
                    models.set_schedule(db, device_id, day, start, end)
                else:
                    models.delete_schedule(db, device_id, day)
            flash('Horarios salvos!', 'success')
        except ValueError as e:
            flash(f'Erro: {e}', 'danger')
        return redirect(url_for('schedule', device_id=device_id))

    schedules_list = models.get_schedules(db, device_id)
    schedules_by_day = {s['day_of_week']: s for s in schedules_list}
    return render_template('schedule.html', device=device, schedules=schedules_by_day, active_tab='schedule')


# --- Contacts ---

@app.route('/devices/<int:device_id>/contacts', methods=['GET', 'POST'])
@login_required
def contacts(device_id):
    device = get_user_device(device_id)
    db = get_db()

    if request.method == 'POST':
        action = request.form.get('action')
        ext = request.form.get('extension', '').strip()
        try:
            if action == 'add' and ext:
                models.add_permission(db, device_id, ext)
                # Verificar se o outro lado ja autorizou este device
                other_device = db.execute(
                    "SELECT d.*, u.email as owner_email FROM devices d "
                    "LEFT JOIN users u ON d.user_id = u.id "
                    "WHERE d.extension = ?", (ext,)
                ).fetchone()
                if other_device and other_device['user_id']:
                    already_allowed = db.execute(
                        "SELECT COUNT(*) as cnt FROM permissions p "
                        "JOIN devices d ON p.device_id = d.id "
                        "WHERE d.extension = ? AND p.allowed_extension = ?",
                        (ext, device['extension'])
                    ).fetchone()['cnt'] > 0
                    if not already_allowed and other_device['owner_email']:
                        try:
                            token = models.create_permission_token(db, device_id, other_device['id'])
                            send_permission_email(
                                other_device['owner_email'],
                                device['child_name'],
                                other_device['child_name'],
                                token
                            )
                            flash(f'Ramal {ext} autorizado. Email enviado para a familia de {other_device["child_name"]}.', 'success')
                        except Exception:
                            logging.exception("Erro ao enviar email de permissao")
                            flash(f'Ramal {ext} autorizado, mas nao foi possivel enviar email.', 'warning')
                    else:
                        flash(f'Ramal {ext} autorizado.', 'success')
                else:
                    flash(f'Ramal {ext} autorizado.', 'success')
            elif action == 'remove' and ext:
                models.remove_permission(db, device_id, ext)
                flash(f'Ramal {ext} removido.', 'success')
        except ValueError as e:
            flash(f'Erro: {e}', 'danger')
        return redirect(url_for('contacts', device_id=device_id))

    my_permissions = models.get_permissions(db, device_id)
    my_allowed = {p['allowed_extension'] for p in my_permissions}

    # Listar todos os outros devices para mostrar status bidirecional
    all_devices = models.get_all_devices(db)
    contact_list = []
    for d in all_devices:
        if d['extension'] == device['extension']:
            continue
        if d['user_id'] is None:
            continue
        i_allow = d['extension'] in my_allowed
        # Verificar se o outro lado tambem autoriza este device
        other_allows = db.execute(
            """SELECT COUNT(*) as cnt FROM permissions p
               JOIN devices od ON p.device_id = od.id
               WHERE od.extension = ? AND p.allowed_extension = ?""",
            (d['extension'], device['extension'])
        ).fetchone()['cnt'] > 0
        activated = d['user_id'] is not None
        if not activated:
            status = 'blocked'
        elif i_allow and other_allows:
            status = 'can_call'
        elif i_allow and not other_allows:
            status = 'waiting_other'
        else:
            status = 'waiting_you'
        contact_list.append({
            'extension': d['extension'],
            'child_name': d['child_name'],
            'i_allow': i_allow,
            'status': status,
        })

    return render_template('contacts.html', device=device, contacts=contact_list, active_tab='contacts')


# --- Call logs ---

@app.route('/devices/<int:device_id>/logs')
@login_required
def call_logs(device_id):
    device = get_user_device(device_id)
    db = get_db()
    logs = models.get_call_logs(db, device['extension'])
    return render_template('call_logs.html', device=device, logs=logs, active_tab='logs')


# --- Admin ---

@app.route('/admin/devices', methods=['GET', 'POST'])
@admin_required
def admin_devices():
    db = get_db()

    if request.method == 'POST':
        extension = request.form.get('extension', '').strip()
        child_name = request.form.get('child_name', '').strip()
        if not extension or not child_name:
            flash('Preencha ramal e nome.', 'danger')
        else:
            existing = db.execute(
                "SELECT id FROM devices WHERE extension = ?", (extension,)
            ).fetchone()
            if existing:
                flash(f'Ramal {extension} ja existe.', 'danger')
            else:
                code = models.generate_registration_code()
                db.execute(
                    "INSERT INTO devices (registration_code, extension, child_name) VALUES (?, ?, ?)",
                    (code, extension, child_name)
                )
                db.commit()
                flash(f'Aparelho criado! Codigo de registro: {code}', 'success')
        return redirect(url_for('admin_devices'))

    all_devs = db.execute(
        """SELECT d.*, u.name as owner_name
           FROM devices d LEFT JOIN users u ON d.user_id = u.id
           ORDER BY d.extension"""
    ).fetchall()
    return render_template('admin_devices.html', devices=all_devs)


# --- Parent call (ligar para os pais) ---

WIZARD_TEMPLATE = """\
[{ext}]
type = wizard
accepts_registrations = yes
sends_registrations = no
accepts_auth = yes
remote_hosts = dynamic
inbound_auth/auth_type = userpass
inbound_auth/username = {ext}
inbound_auth/password = {password}
endpoint/context = telefones-criancas
endpoint/allow = !all,ulaw,alaw,opus,g722
endpoint/direct_media = no
endpoint/rtp_symmetric = yes
endpoint/force_rport = yes
endpoint/rewrite_contact = yes
aor/max_contacts = 1
aor/remove_existing = yes
aor/default_expiration = 120
"""


def create_asterisk_extension(ext, password):
    """Cria ramal no pjsip_wizard.conf e reinicia Asterisk."""
    block = WIZARD_TEMPLATE.format(ext=ext, password=password)
    try:
        # Verificar se ramal ja existe
        result = subprocess.run(
            ['sudo', 'grep', f'\\[{ext}\\]', '/etc/asterisk/pjsip_wizard.conf'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # Ja existe, remover antes de adicionar
            subprocess.run(
                ['sudo', 'sed', '-i', f'/^\\[{ext}\\]$/,/^$/d',
                 '/etc/asterisk/pjsip_wizard.conf'],
                check=True
            )
        subprocess.run(
            ['sudo', 'tee', '-a', '/etc/asterisk/pjsip_wizard.conf'],
            input='\n' + block, capture_output=True, text=True, check=True
        )
        subprocess.run(
            ['sudo', 'systemctl', 'restart', 'asterisk'],
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        logging.exception("Erro ao criar ramal %s no Asterisk", ext)
        return False


def remove_asterisk_extension(ext):
    """Remove ramal do pjsip_wizard.conf e reinicia Asterisk."""
    try:
        subprocess.run(
            ['sudo', 'sed', '-i', f'/^\\[{ext}\\]$/,/^$/d',
             '/etc/asterisk/pjsip_wizard.conf'],
            check=True
        )
        subprocess.run(
            ['sudo', 'systemctl', 'restart', 'asterisk'],
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        logging.exception("Erro ao remover ramal %s do Asterisk", ext)
        return False


@app.route('/devices/<int:device_id>/parent-call', methods=['GET', 'POST'])
@login_required
def parent_call(device_id):
    device = get_user_device(device_id)
    db = get_db()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'activate':
            parent_ext = '9' + device['extension']
            parent_pass = secrets.token_urlsafe(12)
            parent_token = secrets.token_hex(16)

            ok = create_asterisk_extension(parent_ext, parent_pass)
            if ok:
                db.execute(
                    """UPDATE devices
                       SET parent_sip_extension = ?, parent_sip_pass = ?, parent_sip_token = ?
                       WHERE id = ?""",
                    (parent_ext, parent_pass, parent_token, device_id)
                )
                db.commit()
                flash(f'Celular 1 ativado (ramal {parent_ext}).', 'success')
            else:
                flash('Erro ao criar ramal no servidor. Tente novamente.', 'danger')

        elif action == 'deactivate':
            if device['parent_sip_extension']:
                remove_asterisk_extension(device['parent_sip_extension'])
            db.execute(
                """UPDATE devices
                   SET parent_sip_extension = NULL, parent_sip_pass = NULL, parent_sip_token = NULL
                   WHERE id = ?""",
                (device_id,)
            )
            db.commit()
            flash('Celular 1 desativado.', 'success')

        elif action == 'activate2':
            parent_ext = '8' + device['extension']
            parent_pass = secrets.token_urlsafe(12)
            parent_token = secrets.token_hex(16)

            ok = create_asterisk_extension(parent_ext, parent_pass)
            if ok:
                db.execute(
                    """UPDATE devices
                       SET parent2_sip_extension = ?, parent2_sip_pass = ?, parent2_sip_token = ?
                       WHERE id = ?""",
                    (parent_ext, parent_pass, parent_token, device_id)
                )
                db.commit()
                flash(f'Celular 2 ativado (ramal {parent_ext}).', 'success')
            else:
                flash('Erro ao criar ramal no servidor. Tente novamente.', 'danger')

        elif action == 'deactivate2':
            if device['parent2_sip_extension']:
                remove_asterisk_extension(device['parent2_sip_extension'])
            db.execute(
                """UPDATE devices
                   SET parent2_sip_extension = NULL, parent2_sip_pass = NULL, parent2_sip_token = NULL
                   WHERE id = ?""",
                (device_id,)
            )
            db.commit()
            flash('Celular 2 desativado.', 'success')

        return redirect(url_for('parent_call', device_id=device_id))

    # Recarregar device para pegar colunas atualizadas
    device = models.get_device(db, device_id)
    return render_template('parent_call.html', device=device, active_tab='parent_call')


@app.route('/devices/<int:device_id>/parent-call/qr/<int:slot>')
@login_required
def parent_call_qr(device_id, slot):
    device = get_user_device(device_id)
    if slot == 1:
        token = device['parent_sip_token']
    elif slot == 2:
        token = device['parent2_sip_token']
    else:
        abort(404)
    if not token:
        abort(404)
    url = f"provlink://{config.SITE_URL.replace('https://', '').replace('http://', '')}/provision/{token}"
    img = qrcode.make(url, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return Response(buf.getvalue(), mimetype='image/png')


@app.route('/provision/<token>')
def provision(token):
    """Retorna XML de provisioning para Groundwire."""
    db = get_db()
    device = db.execute(
        "SELECT * FROM devices WHERE parent_sip_token = ? OR parent2_sip_token = ?",
        (token, token)
    ).fetchone()
    if not device:
        abort(404)
    # Determinar qual slot (1 ou 2) pelo token
    if device['parent_sip_token'] == token and device['parent_sip_extension']:
        ext = device['parent_sip_extension']
        pwd = device['parent_sip_pass']
    elif device['parent2_sip_token'] == token and device['parent2_sip_extension']:
        ext = device['parent2_sip_extension']
        pwd = device['parent2_sip_pass']
    else:
        abort(404)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<account>
  <title>Telefone {device['child_name']}</title>
  <username>{ext}</username>
  <password>{pwd}</password>
  <host>{config.VPS_IP}</host>
  <transport>tcp</transport>
  <expires>120</expires>
</account>"""
    return Response(xml, mimetype='application/xml')


# --- About ---

@app.route('/sobre')
@login_required
def about():
    return render_template('about.html', active_tab='about')


# --- Init ---

with app.app_context():
    models.init_db(config.DB_PATH)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
