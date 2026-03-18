#!/usr/bin/env python3
"""
log_call.py — AGI script chamado apos Dial() para registrar a chamada com duracao.
"""

import sys
import os
import sqlite3
from datetime import datetime

import pytz

DB_PATH = os.environ.get('TELEFONE_DB_PATH', '/opt/telefone-portal/data/telefone.db')
TIMEZONE = pytz.timezone('America/Sao_Paulo')


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


def main():
    env = agi_read_env()

    caller = env.get('agi_callerid', '')
    destination = agi_get_variable('CALL_DEST')
    dialstatus = agi_get_variable('DIALSTATUS')
    duration_str = agi_get_variable('CALL_DURATION')

    duration = int(duration_str) if duration_str and duration_str.isdigit() else None

    if dialstatus == 'ANSWER' or (duration and duration > 0):
        status = 'ALLOWED'
    elif dialstatus == 'BUSY':
        status = 'BUSY'
    elif dialstatus == 'NOANSWER':
        status = 'NOANSWER'
    elif dialstatus == 'CANCEL':
        status = 'CANCEL'
    else:
        status = 'ALLOWED'

    now = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')

    agi_verbose(f'log_call: {caller} -> {destination} status={status} duration={duration}')

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "INSERT INTO call_logs (caller_ext, callee_ext, timestamp, status, duration_seconds) VALUES (?, ?, ?, ?, ?)",
            (caller, destination, now, status, duration)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        agi_verbose(f'log_call: ERRO: {e}')


if __name__ == '__main__':
    main()
