"""
models.py — Schema SQLite e helpers para o portal de telefonia.
"""

import sqlite3
import os
import re
import secrets
import string
import hashlib
import hmac
from datetime import datetime

DB_PATH = os.environ.get('TELEFONE_DB_PATH', '/opt/telefone-portal/data/telefone.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_code TEXT UNIQUE NOT NULL,
    extension TEXT UNIQUE NOT NULL,
    child_name TEXT NOT NULL,
    user_id INTEGER,
    parent_sip_extension TEXT,
    parent_sip_pass TEXT,
    parent_sip_token TEXT,
    parent2_sip_extension TEXT,
    parent2_sip_pass TEXT,
    parent2_sip_token TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    UNIQUE (device_id, day_of_week)
);

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER NOT NULL,
    allowed_extension TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    UNIQUE (device_id, allowed_extension)
);

CREATE TABLE IF NOT EXISTS call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_ext TEXT NOT NULL,
    callee_ext TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL,
    duration_seconds INTEGER,
    block_reason TEXT
);

CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    token TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS permission_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    from_device_id INTEGER NOT NULL,
    to_device_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_db(db_path=None):
    """Abre conexao SQLite com WAL mode e timeout de 5s."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    """Cria todas as tabelas se nao existirem."""
    conn = get_db(db_path)
    conn.executescript(SCHEMA)
    # Migracao: adicionar colunas parent_sip_* se nao existem
    cols = {row[1] for row in conn.execute("PRAGMA table_info(devices)").fetchall()}
    for col in ['parent_sip_extension', 'parent_sip_pass', 'parent_sip_token',
                 'parent2_sip_extension', 'parent2_sip_pass', 'parent2_sip_token']:
        if col not in cols:
            conn.execute(f"ALTER TABLE devices ADD COLUMN {col} TEXT")
    conn.commit()
    conn.close()


# --- Helpers de senha ---

def hash_password(password):
    """Hash com PBKDF2-SHA256 (100k iteracoes). Resistente a brute force."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000).hex()
    return salt + ':' + h


def check_password(password, password_hash):
    """Verifica senha contra hash PBKDF2. Usa comparacao em tempo constante."""
    salt, h = password_hash.split(':', 1)
    computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(computed, h)


# --- Helpers de registro ---

def generate_registration_code():
    """Gera codigo de 8 caracteres alfanumericos maiusculos."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


# --- Queries de devices ---

def get_devices_for_user(conn, user_id):
    return conn.execute(
        "SELECT * FROM devices WHERE user_id = ?", (user_id,)
    ).fetchall()


def get_device(conn, device_id):
    return conn.execute(
        "SELECT * FROM devices WHERE id = ?", (device_id,)
    ).fetchone()


def link_device(conn, registration_code, user_id):
    """Vincula device ao usuario pelo codigo de registro. Retorna device ou None."""
    device = conn.execute(
        "SELECT * FROM devices WHERE registration_code = ? AND user_id IS NULL",
        (registration_code,)
    ).fetchone()
    if device is None:
        return None
    conn.execute(
        "UPDATE devices SET user_id = ? WHERE id = ?",
        (user_id, device['id'])
    )
    conn.commit()
    return conn.execute("SELECT * FROM devices WHERE id = ?", (device['id'],)).fetchone()


# --- Queries de schedules ---

def get_schedules(conn, device_id):
    """Retorna schedules do device, indexados por day_of_week."""
    rows = conn.execute(
        "SELECT * FROM schedules WHERE device_id = ? ORDER BY day_of_week",
        (device_id,)
    ).fetchall()
    return rows


TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
EXTENSION_RE = re.compile(r'^\d{3}$')


def validate_time(t):
    """Valida formato HH:MM."""
    if not TIME_RE.match(t):
        raise ValueError(f'Horario invalido: {t}')
    return t


def validate_extension(ext):
    """Valida ramal: exatamente 3 digitos."""
    if not EXTENSION_RE.match(ext):
        raise ValueError(f'Ramal invalido: {ext}')
    return ext


def set_schedule(conn, device_id, day_of_week, start_time, end_time):
    """Insere ou atualiza horario para um dia da semana."""
    validate_time(start_time)
    validate_time(end_time)
    conn.execute(
        """INSERT INTO schedules (device_id, day_of_week, start_time, end_time)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (device_id, day_of_week) DO UPDATE
           SET start_time = excluded.start_time, end_time = excluded.end_time""",
        (device_id, day_of_week, start_time, end_time)
    )
    conn.commit()


def delete_schedule(conn, device_id, day_of_week):
    conn.execute(
        "DELETE FROM schedules WHERE device_id = ? AND day_of_week = ?",
        (device_id, day_of_week)
    )
    conn.commit()


# --- Queries de permissions ---

def get_permissions(conn, device_id):
    return conn.execute(
        "SELECT * FROM permissions WHERE device_id = ?", (device_id,)
    ).fetchall()


def add_permission(conn, device_id, allowed_extension):
    validate_extension(allowed_extension)
    conn.execute(
        "INSERT OR IGNORE INTO permissions (device_id, allowed_extension) VALUES (?, ?)",
        (device_id, allowed_extension)
    )
    conn.commit()


def remove_permission(conn, device_id, allowed_extension):
    conn.execute(
        "DELETE FROM permissions WHERE device_id = ? AND allowed_extension = ?",
        (device_id, allowed_extension)
    )
    conn.commit()


def check_bidirectional_permission(conn, ext_a, ext_b):
    """Verifica se A autorizou B E B autorizou A."""
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM permissions p
           JOIN devices d ON p.device_id = d.id
           WHERE (d.extension = ? AND p.allowed_extension = ?)
              OR (d.extension = ? AND p.allowed_extension = ?)""",
        (ext_a, ext_b, ext_b, ext_a)
    ).fetchone()
    return row['cnt'] >= 2


# --- Queries de horario (para AGI) ---

def check_schedule_now(conn, extension, now=None):
    """Verifica se o ramal esta dentro do horario permitido agora."""
    if now is None:
        now = datetime.now()
    day = now.weekday()  # 0=segunda ... 6=domingo
    current_time = now.strftime('%H:%M')
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM schedules s
           JOIN devices d ON s.device_id = d.id
           WHERE d.extension = ? AND s.day_of_week = ?
             AND s.start_time <= ? AND s.end_time > ?""",
        (extension, day, current_time, current_time)
    ).fetchone()
    return row['cnt'] > 0


# --- Queries de call_logs ---

def log_call(conn, caller_ext, callee_ext, status, block_reason=None):
    conn.execute(
        """INSERT INTO call_logs (caller_ext, callee_ext, status, block_reason)
           VALUES (?, ?, ?, ?)""",
        (caller_ext, callee_ext, status, block_reason)
    )
    conn.commit()


def get_call_logs(conn, extension, limit=50):
    return conn.execute(
        """SELECT * FROM call_logs
           WHERE caller_ext = ? OR callee_ext = ?
           ORDER BY timestamp DESC LIMIT ?""",
        (extension, extension, limit)
    ).fetchall()


# --- Queries de todos os devices (para contacts) ---

def get_all_devices(conn):
    return conn.execute(
        "SELECT * FROM devices ORDER BY extension"
    ).fetchall()


# --- Password reset ---

def create_reset_token(conn, email):
    """Gera token de reset, limpa tokens anteriores do email, retorna token."""
    conn.execute("DELETE FROM password_resets WHERE email = ?", (email,))
    token = secrets.token_hex(32)
    conn.execute(
        "INSERT INTO password_resets (email, token) VALUES (?, ?)",
        (email, token)
    )
    conn.commit()
    return token


def validate_reset_token(conn, token):
    """Retorna email se token existe e tem menos de 1 hora. Senao None."""
    row = conn.execute(
        """SELECT email FROM password_resets
           WHERE token = ? AND datetime(created_at, '+1 hour') > datetime('now')""",
        (token,)
    ).fetchone()
    return row['email'] if row else None


def delete_reset_token(conn, token):
    conn.execute("DELETE FROM password_resets WHERE token = ?", (token,))
    conn.commit()


# --- Permission tokens (autorizacao por email) ---

def create_permission_token(conn, from_device_id, to_device_id):
    """Gera token para autorizar permissao reversa. Retorna token hex 32 chars."""
    token = secrets.token_hex(32)
    conn.execute(
        "INSERT INTO permission_tokens (token, from_device_id, to_device_id) VALUES (?, ?, ?)",
        (token, from_device_id, to_device_id)
    )
    conn.commit()
    return token


def validate_permission_token(conn, token):
    """Retorna (from_device_id, to_device_id) se token valido e < 7 dias. Senao None."""
    row = conn.execute(
        """SELECT from_device_id, to_device_id FROM permission_tokens
           WHERE token = ? AND datetime(created_at, '+7 days') > datetime('now')""",
        (token,)
    ).fetchone()
    if row:
        return (row['from_device_id'], row['to_device_id'])
    return None


def delete_permission_token(conn, token):
    conn.execute("DELETE FROM permission_tokens WHERE token = ?", (token,))
    conn.commit()


# --- Exclusao de conta ---

def delete_account(conn, user_id):
    """Remove todos os dados de um usuario e seus devices.
    Retorna lista de extensions (child + parent) para remover do Asterisk."""
    devices = conn.execute(
        "SELECT id, extension, parent_sip_extension, parent2_sip_extension FROM devices WHERE user_id = ?",
        (user_id,)
    ).fetchall()

    device_ids = [d['id'] for d in devices]
    extensions = [d['extension'] for d in devices]
    # Extensoes para remover do Asterisk: child (067) + parent (9067, 8067) se existirem
    asterisk_extensions = list(extensions)
    for d in devices:
        if d['parent_sip_extension']:
            asterisk_extensions.append(d['parent_sip_extension'])
        if d['parent2_sip_extension']:
            asterisk_extensions.append(d['parent2_sip_extension'])

    for dev_id in device_ids:
        conn.execute("DELETE FROM schedules WHERE device_id = ?", (dev_id,))
        conn.execute("DELETE FROM permissions WHERE device_id = ?", (dev_id,))
        conn.execute("DELETE FROM permission_tokens WHERE from_device_id = ? OR to_device_id = ?", (dev_id, dev_id))

    # Remover permissoes que outros tem apontando para os ramais deste usuario
    for ext in extensions:
        conn.execute("DELETE FROM permissions WHERE allowed_extension = ?", (ext,))

    # Remover call_logs envolvendo os ramais
    for ext in extensions:
        conn.execute("DELETE FROM call_logs WHERE caller_ext = ? OR callee_ext = ?", (ext, ext))

    # Deletar devices completamente
    for dev_id in device_ids:
        conn.execute("DELETE FROM devices WHERE id = ?", (dev_id,))

    # Remover password resets e usuario
    user = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        conn.execute("DELETE FROM password_resets WHERE email = ?", (user['email'],))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    # Limpar tokens orfaos (devices que nao existem mais)
    conn.execute("""DELETE FROM permission_tokens
                    WHERE from_device_id NOT IN (SELECT id FROM devices)
                       OR to_device_id NOT IN (SELECT id FROM devices)""")

    conn.commit()
    return asterisk_extensions
