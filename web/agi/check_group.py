#!/usr/bin/env python3
"""
check_group.py — AGI script para Asterisk.
Verifica se o caller tem permissao mutua com TODOS os participantes de uma
chamada em grupo antes de permitir a entrada.

O dialplan passa a lista de membros atuais via variavel CONF_MEMBERS.
"""

import sys
import os
import sqlite3

DB_PATH = os.environ.get('TELEFONE_DB_PATH', '/opt/telefone-portal/data/telefone.db')


def agi_read_env():
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
    sys.stdout.write(f'SET VARIABLE {name} "{value}"\n')
    sys.stdout.flush()
    sys.stdin.readline()


def agi_get_variable(name):
    sys.stdout.write(f'GET VARIABLE {name}\n')
    sys.stdout.flush()
    result = sys.stdin.readline().strip()
    if '(' in result and ')' in result:
        return result.split('(', 1)[1].rsplit(')', 1)[0]
    return ''


def agi_verbose(msg):
    sys.stdout.write(f'VERBOSE "{msg}" 3\n')
    sys.stdout.flush()
    sys.stdin.readline()


def check_permission(conn, ext1, ext2):
    """Verifica permissao bidirecional entre dois ramais."""
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM permissions p
           JOIN devices d ON p.device_id = d.id
           WHERE (d.extension = ? AND p.allowed_extension = ?)
              OR (d.extension = ? AND p.allowed_extension = ?)""",
        (ext1, ext2, ext2, ext1)
    ).fetchone()
    return row['cnt'] >= 2


def main():
    env = agi_read_env()

    caller = env.get('agi_callerid', '')
    if '<' in caller and '>' in caller:
        caller = caller.split('<')[1].split('>')[0]
    caller = caller.strip('"').strip()

    members_str = agi_get_variable('CONF_MEMBERS')
    if not members_str:
        agi_verbose('check_group: sem lista de membros')
        agi_set_variable('GROUP_RESULT', 'BLOCK')
        return

    members = [m.strip() for m in members_str.split(',') if m.strip()]
    agi_verbose(f'check_group: caller={caller} membros={members}')

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
    except Exception as e:
        agi_verbose(f'check_group: ERRO ao abrir banco: {e}')
        agi_set_variable('GROUP_RESULT', 'BLOCK')
        return

    for member in members:
        if member == caller:
            continue
        if not check_permission(conn, caller, member):
            agi_verbose(f'check_group: sem permissao {caller} <-> {member}')
            agi_set_variable('GROUP_RESULT', 'BLOCK')
            conn.close()
            return

    agi_verbose(f'check_group: PERMITIDO {caller} entrar no grupo')
    agi_set_variable('GROUP_RESULT', 'ALLOW')
    conn.close()


if __name__ == '__main__':
    main()
