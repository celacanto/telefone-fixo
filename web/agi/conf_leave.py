#!/usr/bin/env python3
"""
conf_leave.py — AGI script chamado quando um participante sai de uma conferencia.
Calcula tempo com cada participante (incluindo quem ja saiu), seta GRUPO_DETALHE,
e limpa AstDB. Idempotente (seguro chamar mais de uma vez).
"""

import sys
import time


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


def agi_set_variable(name, value):
    sys.stdout.write(f'SET VARIABLE {name} "{value}"\n')
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
        return

    agi_verbose(f'conf_leave: {my_ext} saindo da conferencia {conf_room}')

    now = int(time.time())

    # Meu horario de entrada
    my_join_str = agi_database_get('confroom', f'{conf_room}/join/{my_ext}')
    my_join = int(my_join_str) if my_join_str and my_join_str.isdigit() else now

    # Registrar meu horario de saida (para quem sair depois de mim)
    agi_database_put('confroom', f'{conf_room}/left/{my_ext}', str(now))

    # Lista de TODOS que participaram da conferencia
    all_members_str = agi_database_get('confroom', f'{conf_room}/all_members')
    if not all_members_str:
        all_members_str = agi_database_get('confroom', f'{conf_room}/members')
    if not all_members_str:
        agi_database_del('confbridge', my_ext)
        agi_database_deltree('confroom', conf_room)
        return

    all_members = [m.strip() for m in all_members_str.split(',') if m.strip()]
    others = [m for m in all_members if m != my_ext]

    # Calcular overlap com cada outro participante
    details = []
    for other in others:
        other_join_str = agi_database_get('confroom', f'{conf_room}/join/{other}')
        if not other_join_str or not other_join_str.isdigit():
            continue
        other_join = int(other_join_str)

        # Se o outro ja saiu, usar o horario de saida dele; senao, agora
        other_left_str = agi_database_get('confroom', f'{conf_room}/left/{other}')
        if other_left_str and other_left_str.isdigit():
            other_end = int(other_left_str)
        else:
            other_end = now  # ainda na sala

        # Overlap = min(minha_saida, saida_outro) - max(minha_entrada, entrada_outro)
        overlap = min(now, other_end) - max(my_join, other_join)
        if overlap > 0:
            details.append(f'{other}:{overlap}')

    if details:
        grupo_detalhe = ','.join(details)
        agi_set_variable('GRUPO_DETALHE', grupo_detalhe)
        agi_verbose(f'conf_leave: {my_ext} detalhe={grupo_detalhe}')

    # Remover do tracking ativo
    agi_database_del('confbridge', my_ext)

    # Atualizar lista de membros ativos
    members_str = agi_database_get('confroom', f'{conf_room}/members')
    if not members_str:
        agi_database_deltree('confroom', conf_room)
        return

    remaining = [m for m in members_str.split(',') if m.strip() and m.strip() != my_ext]

    if len(remaining) == 0:
        # Ultimo a sair — limpar tudo
        agi_database_deltree('confroom', conf_room)
        agi_verbose(f'conf_leave: conferencia {conf_room} encerrada (ultimo)')
    elif len(remaining) == 1:
        # Penultimo a sair — manter dados para o ultimo calcular overlap,
        # mas fechar a sala e limpar ponteiro para evitar dados residuais
        # caso o conf_leave do ultimo nao execute (crash, timeout, etc.)
        agi_database_put('confroom', f'{conf_room}/members', ','.join(remaining))
        agi_database_put('confroom', f'{conf_room}/count', '1')
        agi_database_put('confroom', f'{conf_room}/open', '0')
        agi_database_del('confbridge', remaining[0])
        agi_verbose(f'conf_leave: 1 restante em {conf_room} (sala fechada)')
    else:
        # Varios restantes
        agi_database_put('confroom', f'{conf_room}/members', ','.join(remaining))
        agi_database_put('confroom', f'{conf_room}/count', str(len(remaining)))
        agi_verbose(f'conf_leave: {len(remaining)} restantes em {conf_room}')


if __name__ == '__main__':
    main()
