#!/usr/bin/env python3
"""
check_call.py — AGI script para Asterisk.
Verifica horario e permissoes no SQLite antes de permitir chamadas.

Instalacao: copiar para /var/lib/asterisk/agi-bin/check_call.py
            chmod +x check_call.py
"""

import sys
import os
import sqlite3
from datetime import datetime

import pytz

DB_PATH = os.environ.get('TELEFONE_DB_PATH', '/opt/telefone-portal/data/telefone.db')
TIMEZONE = pytz.timezone('America/Sao_Paulo')
BYPASS_EXTENSIONS = {'100'}  # hora certa — sempre disponivel


def agi_read_env():
    """Le variaveis AGI do stdin."""
    env = {}
    while True:
        line = sys.stdin.readline().strip()
        if line == '':
            break
        if ':' in line:
            key, _, value = line.partition(':')
            env[key.strip()] = value.strip()
    return env


def agi_set_variable(name, value):
    """Envia SET VARIABLE via AGI."""
    sys.stdout.write(f'SET VARIABLE {name} "{value}"\n')
    sys.stdout.flush()
    sys.stdin.readline()  # le resposta do Asterisk


def agi_verbose(msg):
    sys.stdout.write(f'VERBOSE "{msg}" 3\n')
    sys.stdout.flush()
    sys.stdin.readline()


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def check_schedule(conn, extension, now):
    """Verifica se ramal esta dentro do horario permitido.
    Sem horario configurado para o dia = liberado o dia todo."""
    day = now.weekday()  # 0=segunda ... 6=domingo
    current_time = now.strftime('%H:%M')
    # Verifica se existe algum horario configurado para este dia
    has_schedule = conn.execute(
        """SELECT COUNT(*) as cnt FROM schedules s
           JOIN devices d ON s.device_id = d.id
           WHERE d.extension = ? AND s.day_of_week = ?""",
        (extension, day)
    ).fetchone()['cnt'] > 0
    if not has_schedule:
        return True  # sem restricao = liberado
    # Se tem horario configurado, verifica se esta dentro
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM schedules s
           JOIN devices d ON s.device_id = d.id
           WHERE d.extension = ? AND s.day_of_week = ?
             AND s.start_time <= ? AND s.end_time > ?""",
        (extension, day, current_time, current_time)
    ).fetchone()
    return row['cnt'] > 0


def check_permission(conn, caller, callee):
    """Verifica permissao bidirecional."""
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM permissions p
           JOIN devices d ON p.device_id = d.id
           WHERE (d.extension = ? AND p.allowed_extension = ?)
              OR (d.extension = ? AND p.allowed_extension = ?)""",
        (caller, callee, callee, caller)
    ).fetchone()
    return row['cnt'] >= 2


def log_call(conn, caller, callee, status, reason=None):
    now = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "INSERT INTO call_logs (caller_ext, callee_ext, timestamp, status, block_reason) VALUES (?, ?, ?, ?, ?)",
        (caller, callee, now, status, reason)
    )
    conn.commit()


def is_parent_extension(ext):
    """Verifica se e um ramal de pai (9 ou 8 + 3 digitos)."""
    return len(ext) == 4 and ext[0] in ('9', '8') and ext[1:].isdigit()


def check_parent_call(conn, caller, destination, now):
    """Verifica chamadas envolvendo ramal de pai.
    Retorna (allowed, block_reason) ou None se nao e chamada de pai."""

    caller_is_parent = is_parent_extension(caller)
    dest_is_parent = is_parent_extension(destination)

    if not caller_is_parent and not dest_is_parent:
        return None  # chamada normal entre criancas

    if dest_is_parent:
        # Crianca ligando para pai: verificar que o destino e o pai DESTE caller
        device = conn.execute(
            """SELECT * FROM devices WHERE extension = ?
               AND (parent_sip_extension = ? OR parent2_sip_extension = ?)
               AND user_id IS NOT NULL""",
            (caller, destination, destination)
        ).fetchone()
        if device is None:
            return (False, 'PARENT_NOT_LINKED')
        return (True, None)

    if caller_is_parent:
        # Pai ligando para crianca: verificar que o caller e o pai do destino
        device = conn.execute(
            """SELECT * FROM devices WHERE extension = ?
               AND (parent_sip_extension = ? OR parent2_sip_extension = ?)
               AND user_id IS NOT NULL""",
            (destination, caller, caller)
        ).fetchone()
        if device is None:
            return (False, 'PARENT_NOT_LINKED')
        return (True, None)

    return None


def main():
    env = agi_read_env()

    caller = env.get('agi_callerid', '')
    destination = env.get('agi_extension', '')

    # Se argumento AGI fornecido, usar como destino (chamada em grupo *XXX)
    if env.get('agi_arg_1'):
        destination = env['agi_arg_1']

    # Se callerid vier com nome, extrair so o numero
    if '<' in caller and '>' in caller:
        caller = caller.split('<')[1].split('>')[0]
    # Remover aspas
    caller = caller.strip('"').strip()

    agi_verbose(f'check_call: caller={caller} dest={destination}')

    # Bypass para ramais especiais
    if destination in BYPASS_EXTENSIONS:
        agi_set_variable('CALL_RESULT', 'ALLOW')
        return

    try:
        conn = get_db()
    except Exception as e:
        agi_verbose(f'check_call: ERRO ao abrir banco: {e}')
        agi_set_variable('CALL_RESULT', 'BLOCK_ERROR')  # fail-closed: na duvida, bloqueia
        return

    now = datetime.now(TIMEZONE)

    # Verificar se e chamada envolvendo ramal de pai
    parent_result = check_parent_call(conn, caller, destination, now)
    if parent_result is not None:
        allowed, reason = parent_result
        if allowed:
            agi_verbose(f'check_call: PERMITIDO (pai) {caller} -> {destination}')
            agi_set_variable('CALL_RESULT', 'ALLOW')
        else:
            agi_verbose(f'check_call: BLOQUEADO (pai) {caller} -> {destination}: {reason}')
            log_call(conn, caller, destination, 'BLOCKED', reason)
            agi_set_variable('CALL_RESULT', 'BLOCK_PARENT')
        conn.close()
        return

    # --- Chamada normal entre criancas ---

    # Verificar se caller existe como device ativado
    caller_device = conn.execute(
        "SELECT id FROM devices WHERE extension = ? AND user_id IS NOT NULL",
        (caller,)
    ).fetchone()
    if caller_device is None:
        agi_verbose(f'check_call: caller {caller} nao ativado')
        log_call(conn, caller, destination, 'BLOCKED', 'CALLER_NOT_ACTIVATED')
        agi_set_variable('CALL_RESULT', 'BLOCK_UNKNOWN')
        conn.close()
        return

    # Verificar se destino existe como device ativado
    dest_device = conn.execute(
        "SELECT id FROM devices WHERE extension = ? AND user_id IS NOT NULL",
        (destination,)
    ).fetchone()
    if dest_device is None:
        agi_verbose(f'check_call: destino {destination} nao encontrado')
        log_call(conn, caller, destination, 'BLOCKED', 'UNKNOWN_DEST')
        agi_set_variable('CALL_RESULT', 'BLOCK_UNKNOWN')
        conn.close()
        return

    # Verificar horario do caller
    if not check_schedule(conn, caller, now):
        agi_verbose(f'check_call: {caller} fora do horario')
        log_call(conn, caller, destination, 'BLOCKED', 'SCHEDULE_CALLER')
        agi_set_variable('CALL_RESULT', 'BLOCK_SCHEDULE_CALLER')
        conn.close()
        return

    # Verificar horario do destino
    if not check_schedule(conn, destination, now):
        agi_verbose(f'check_call: {destination} fora do horario')
        log_call(conn, caller, destination, 'BLOCKED', 'SCHEDULE_DEST')
        agi_set_variable('CALL_RESULT', 'BLOCK_SCHEDULE_DEST')
        conn.close()
        return

    # Verificar permissao bidirecional
    if not check_permission(conn, caller, destination):
        agi_verbose(f'check_call: sem permissao {caller} <-> {destination}')
        log_call(conn, caller, destination, 'BLOCKED', 'PERMISSION')
        agi_set_variable('CALL_RESULT', 'BLOCK_PERMISSION')
        conn.close()
        return

    # Tudo OK — nao loga aqui, loga depois do Dial com duracao
    agi_verbose(f'check_call: PERMITIDO {caller} -> {destination}')
    agi_set_variable('CALL_RESULT', 'ALLOW')
    conn.close()


if __name__ == '__main__':
    main()
