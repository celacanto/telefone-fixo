#!/usr/bin/env python3
"""
conf_leave.py — AGI script chamado quando um participante sai de uma conferencia.
Limpa entradas do AstDB. Idempotente (seguro chamar mais de uma vez).
"""

import sys


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


def agi_verbose(msg):
    sys.stdout.write(f'VERBOSE "{msg}" 3\n')
    sys.stdout.flush()
    sys.stdin.readline()


def agi_database_get(family, key):
    sys.stdout.write(f'DATABASE GET {family} {key}\n')
    sys.stdout.flush()
    result = sys.stdin.readline().strip()
    if 'result=1' in result and '(' in result:
        return result.split('(', 1)[1].rsplit(')', 1)[0]
    return None


def agi_database_put(family, key, value):
    sys.stdout.write(f'DATABASE PUT {family} {key} {value}\n')
    sys.stdout.flush()
    sys.stdin.readline()


def agi_database_del(family, key):
    sys.stdout.write(f'DATABASE DEL {family} {key}\n')
    sys.stdout.flush()
    sys.stdin.readline()


def agi_database_deltree(family, keytree=None):
    if keytree:
        sys.stdout.write(f'DATABASE DELTREE {family} {keytree}\n')
    else:
        sys.stdout.write(f'DATABASE DELTREE {family}\n')
    sys.stdout.flush()
    sys.stdin.readline()


def get_extension_from_channel(channel):
    """Extrai ramal do nome do canal PJSIP/067-00000001 -> 067."""
    if '/' in channel and '-' in channel:
        return channel.split('/')[1].split('-')[0]
    if '/' in channel:
        return channel.split('/')[1]
    return None


def main():
    env = agi_read_env()

    channel = env.get('agi_channel', '')
    my_ext = get_extension_from_channel(channel)
    if not my_ext:
        agi_verbose(f'conf_leave: nao conseguiu extrair ramal de {channel}')
        return

    conf_room = agi_database_get('confbridge', my_ext)
    if not conf_room:
        # Nao esta em conferencia (ou ja foi limpo) — nada a fazer
        return

    agi_verbose(f'conf_leave: {my_ext} saindo da conferencia {conf_room}')

    # Remover este participante do rastreamento
    agi_database_del('confbridge', my_ext)

    # Atualizar lista de membros
    members_str = agi_database_get('confroom', f'{conf_room}/members')
    if not members_str:
        # Dados inconsistentes — limpar tudo
        agi_database_deltree('confroom', conf_room)
        return

    remaining = [m for m in members_str.split(',') if m.strip() and m.strip() != my_ext]

    if len(remaining) <= 1:
        # Conferencia acabou (0 ou 1 pessoa restante)
        # Remover entrada do ultimo participante (se houver)
        for m in remaining:
            agi_database_del('confbridge', m)
        # Limpar toda a sala
        agi_database_deltree('confroom', conf_room)
        agi_verbose(f'conf_leave: conferencia {conf_room} encerrada')
    else:
        # Atualizar membros e contagem
        agi_database_put('confroom', f'{conf_room}/members', ','.join(remaining))
        agi_database_put('confroom', f'{conf_room}/count', str(len(remaining)))
        agi_verbose(f'conf_leave: {len(remaining)} restantes em {conf_room}')


if __name__ == '__main__':
    main()
