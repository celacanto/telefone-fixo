#!/usr/bin/env python3
"""
migrate.py — Cria a conta admin inicial no banco de dados.

Executar uma unica vez apos o deploy:
  sudo /opt/telefone-portal/venv/bin/python /opt/telefone-portal/migrate.py
"""

import os
import sys

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
    else:
        pw_hash = models.hash_password('admin123')
        conn.execute(
            "INSERT INTO users (email, password_hash, name, is_admin) VALUES (?, ?, ?, 1)",
            ('admin@telefone.local', pw_hash, 'Admin')
        )
        conn.commit()
        print("Conta admin criada — email: admin@telefone.local, senha: admin123")
        print("  ** TROQUE A SENHA APOS O PRIMEIRO LOGIN **")

    conn.close()
    print("\nMigracao concluida!")
    print("\nProximos passos:")
    print("  1. Faca login no portal com admin@telefone.local / admin123")
    print("  2. Troque a senha imediatamente")
    print("  3. Crie os devices (telefones) na aba Admin")


if __name__ == '__main__':
    main()
