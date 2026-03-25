#!/usr/bin/env python3
"""
hora_certa.py — AGI que fala a hora atual em portugues brasileiro.
Usa frases completas pre-gravadas em /usr/share/asterisk/sounds/hora/

Exemplo: 14:35 -> "quatorze horas" + "e trinta e cinco minutos"
         13:00 -> "treze horas"
         00:30 -> "zero hora" + "e meia"
"""

import sys
from datetime import datetime
import pytz

TIMEZONE = pytz.timezone('America/Sao_Paulo')
SOUND_DIR = 'hora'


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


def agi_exec(app, args=''):
    sys.stdout.write(f'EXEC {app} "{args}"\n')
    sys.stdout.flush()
    sys.stdin.readline()


def main():
    agi_read_env()

    now = datetime.now(TIMEZONE)
    hora = now.hour
    minuto = now.minute

    # Tocar a hora (ex: "quatorze horas")
    agi_exec('Playback', f'{SOUND_DIR}/h{hora}')

    # Tocar os minutos se houver (ex: "e trinta e cinco minutos")
    if minuto > 0:
        agi_exec('Playback', f'{SOUND_DIR}/m{minuto}')


if __name__ == '__main__':
    main()
