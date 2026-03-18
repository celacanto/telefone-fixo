"""
config.py — Configuracoes do portal de telefonia.
"""

import os
import secrets

SECRET_KEY = os.environ.get('TELEFONE_SECRET_KEY', secrets.token_hex(32))
DB_PATH = os.environ.get('TELEFONE_DB_PATH', '/opt/telefone-portal/data/telefone.db')
VPS_IP = '163.176.157.229'

# SMTP (Gmail)
SMTP_HOST = os.environ.get('TELEFONE_SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('TELEFONE_SMTP_PORT', '587'))
SMTP_USER = os.environ.get('TELEFONE_SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('TELEFONE_SMTP_PASSWORD', '')
SITE_URL = os.environ.get('TELEFONE_SITE_URL', 'https://telefone-fixo.duckdns.org')
