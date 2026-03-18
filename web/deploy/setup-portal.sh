#!/bin/bash
# =============================================================================
# setup-portal.sh — Deploy do portal web no VPS
# Executar via SSH no servidor: bash setup-portal.sh
# =============================================================================

set -euo pipefail

PORTAL_DIR="/opt/telefone-portal"
DATA_DIR="$PORTAL_DIR/data"
AGI_DIR="/var/lib/asterisk/agi-bin"
VENV_DIR="$PORTAL_DIR/venv"

echo "=== Instalando dependencias do sistema ==="
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip nginx

echo "=== Criando estrutura de diretorios ==="
sudo mkdir -p "$PORTAL_DIR"/{templates,static,data}
sudo mkdir -p "$AGI_DIR"

echo "=== Copiando arquivos do portal ==="
# Estes arquivos devem ser transferidos via scp antes de rodar este script
# scp -i ssh-key-2026-03-02.key -r web/* ubuntu@163.176.157.229:/tmp/portal/
if [ -d /tmp/portal ]; then
    sudo cp /tmp/portal/app.py "$PORTAL_DIR/"
    sudo cp /tmp/portal/models.py "$PORTAL_DIR/"
    sudo cp /tmp/portal/config.py "$PORTAL_DIR/"
    sudo cp /tmp/portal/requirements.txt "$PORTAL_DIR/"
    sudo cp /tmp/portal/templates/* "$PORTAL_DIR/templates/"
    sudo cp /tmp/portal/static/* "$PORTAL_DIR/static/"
    sudo cp /tmp/portal/agi/check_call.py "$AGI_DIR/check_call.py"
    sudo chmod +x "$AGI_DIR/check_call.py"
    sudo cp /tmp/portal/migrate.py "$PORTAL_DIR/"
else
    echo "ERRO: Copie os arquivos para /tmp/portal/ primeiro."
    echo "  scp -i ssh-key-2026-03-02.key -r web/* ubuntu@IP:/tmp/portal/"
    exit 1
fi

echo "=== Criando venv e instalando Flask ==="
sudo python3 -m venv "$VENV_DIR"
sudo "$VENV_DIR/bin/pip" install -q -r "$PORTAL_DIR/requirements.txt"

echo "=== Gerando SECRET_KEY ==="
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

echo "=== Configurando systemd ==="
sudo tee /etc/systemd/system/telefone-portal.service > /dev/null <<EOF
[Unit]
Description=Telefone Fixo - Portal Web para Pais
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$PORTAL_DIR
Environment=TELEFONE_DB_PATH=$DATA_DIR/telefone.db
Environment=TELEFONE_SECRET_KEY=$SECRET_KEY
Environment=TELEFONE_SMTP_USER=rede.telefonefixo@gmail.com
Environment="TELEFONE_SMTP_PASSWORD=kpjy dlya aoml scoi"
Environment=FLASK_APP=app.py
ExecStart=$VENV_DIR/bin/python -m flask run --host=127.0.0.1 --port=5000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "=== Ajustando permissoes ==="
sudo chown -R www-data:www-data "$PORTAL_DIR"
# AGI roda como asterisk
sudo chown asterisk:asterisk "$AGI_DIR/check_call.py"
# O banco precisa ser legivel pelo asterisk (AGI) e www-data (Flask)
sudo chmod 775 "$DATA_DIR"
sudo usermod -aG www-data asterisk 2>/dev/null || true

echo "=== Configurando nginx ==="
if [ -f /tmp/portal/deploy/nginx-telefone.conf ]; then
    sudo cp /tmp/portal/deploy/nginx-telefone.conf /etc/nginx/sites-available/telefone
    sudo ln -sf /etc/nginx/sites-available/telefone /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t && sudo systemctl reload nginx
fi

echo "=== Abrindo portas 80 e 443 no iptables ==="
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || true

echo "=== Iniciando servico ==="
sudo systemctl daemon-reload
sudo systemctl enable telefone-portal
sudo systemctl start telefone-portal

echo "=== Verificando status ==="
sudo systemctl status telefone-portal --no-pager

echo ""
echo "=== Deploy concluido! ==="
echo "Portal rodando em http://localhost:5000"
echo "nginx em http://$(hostname -I | awk '{print $1}')"
echo ""
echo "Proximos passos:"
echo "  1. Configurar DuckDNS: editar /etc/nginx/sites-available/telefone com o dominio"
echo "  2. Certbot: sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx"
echo "  3. Abrir portas 80/443 nas Security Lists da Oracle Cloud"
echo "  4. Rodar o script de migracao: sudo $VENV_DIR/bin/python $PORTAL_DIR/migrate.py"
echo "  5. Trocar extensions.conf: sudo cp /tmp/portal/deploy/extensions.conf.new /etc/asterisk/extensions.conf"
echo "     Depois: sudo systemctl restart asterisk"
