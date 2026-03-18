#!/usr/bin/env python3
"""
migrate.py — Popula o banco com dados existentes do sistema de telefonia.

Cria:
- Conta admin (Daniel)
- Devices para ramais 067 (Inacio), 002 (Madalena), 001 (reserva)
- Schedules 10:00-22:00 todos os dias (comportamento atual)
- Permissions mutuas 067 <-> 002
- Gera codigos de registro para cada device

Executar uma unica vez apos o deploy:
  sudo /opt/telefone-portal/venv/bin/python /opt/telefone-portal/migrate.py
"""

import os
import sys

# Permitir import quando executado direto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import models

DB_PATH = os.environ.get('TELEFONE_DB_PATH', '/opt/telefone-portal/data/telefone.db')


def main():
    print(f"Banco: {DB_PATH}")
    models.init_db(DB_PATH)
    conn = models.get_db(DB_PATH)

    # --- Conta admin ---
    existing = conn.execute("SELECT id FROM users WHERE email = 'admin@telefone.local'").fetchone()
    if existing:
        print("Conta admin ja existe, pulando.")
        admin_id = existing['id']
    else:
        pw_hash = models.hash_password('admin123')  # TROCAR APOS PRIMEIRO LOGIN
        conn.execute(
            "INSERT INTO users (email, password_hash, name, is_admin) VALUES (?, ?, ?, 1)",
            ('admin@telefone.local', pw_hash, 'Daniel', )
        )
        conn.commit()
        admin_id = conn.execute("SELECT id FROM users WHERE email = 'admin@telefone.local'").fetchone()['id']
        print(f"Conta admin criada (id={admin_id}) — email: admin@telefone.local, senha: admin123")
        print("  ** TROQUE A SENHA APOS O PRIMEIRO LOGIN **")

    # --- Devices ---
    devices_data = [
        ('067', 'Inacio', admin_id),
        ('002', 'Madalena', admin_id),
        ('001', 'Reserva', None),
    ]

    device_ids = {}
    for ext, name, user_id in devices_data:
        existing = conn.execute("SELECT id, registration_code FROM devices WHERE extension = ?", (ext,)).fetchone()
        if existing:
            print(f"Device {ext} ja existe (codigo: {existing['registration_code']}), pulando.")
            device_ids[ext] = existing['id']
        else:
            code = models.generate_registration_code()
            conn.execute(
                "INSERT INTO devices (registration_code, extension, child_name, user_id) VALUES (?, ?, ?, ?)",
                (code, ext, name, user_id)
            )
            conn.commit()
            device_ids[ext] = conn.execute("SELECT id FROM devices WHERE extension = ?", (ext,)).fetchone()['id']
            print(f"Device criado: {ext} ({name}) — codigo: {code}")

    # --- Schedules (10:00-22:00 todos os dias) ---
    for ext in ['067', '002']:
        dev_id = device_ids[ext]
        existing = conn.execute("SELECT COUNT(*) as cnt FROM schedules WHERE device_id = ?", (dev_id,)).fetchone()
        if existing['cnt'] > 0:
            print(f"Schedules para {ext} ja existem, pulando.")
            continue
        for day in range(7):  # 0=segunda ... 6=domingo
            models.set_schedule(conn, dev_id, day, '10:00', '22:00')
        print(f"Schedules criados para {ext}: 10:00-22:00, todos os dias")

    # --- Permissions mutuas 067 <-> 002 ---
    for ext_a, ext_b in [('067', '002'), ('002', '067')]:
        dev_id = device_ids[ext_a]
        existing = conn.execute(
            "SELECT id FROM permissions WHERE device_id = ? AND allowed_extension = ?",
            (dev_id, ext_b)
        ).fetchone()
        if existing:
            print(f"Permissao {ext_a} -> {ext_b} ja existe, pulando.")
        else:
            models.add_permission(conn, dev_id, ext_b)
            print(f"Permissao criada: {ext_a} -> {ext_b}")

    conn.close()
    print("\nMigracao concluida!")
    print("\nProximo passo: trocar extensions.conf e reiniciar Asterisk")


if __name__ == '__main__':
    main()
