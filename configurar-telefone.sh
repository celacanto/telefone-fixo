#!/bin/bash
# =============================================================================
# configurar-telefone.sh — Configura um HT802 novo + adiciona ramal no servidor
#
# Uso: bash configurar-telefone.sh
#
# O script vai pedir:
#   - IP do HT802 na rede local (ex: 192.168.1.85)
#   - Senha admin do HT802 (ver etiqueta no aparelho)
#   - Número do ramal (ex: 002)
#   - Nome da criança (ex: Pedro)
#
# Ele vai:
#   1. Gerar uma senha SIP forte
#   2. Configurar o HT802 automaticamente via HTTP API
#   3. Adicionar o ramal no servidor Asterisk
#   4. Reiniciar o HT802
# =============================================================================

set -euo pipefail

# --- Configurações fixas ---
VPS_IP="163.176.157.229"
SSH_KEY="$(dirname "$0")/ssh-key-2026-03-02.key"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Cores ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo " Configurar Novo Telefone"
echo "========================================="
echo ""

# --- Coleta dados ---
read -p "IP do HT802 na rede local (ex: 192.168.1.85): " HT_IP
read -p "Senha admin do HT802 (ver etiqueta no aparelho): " HT_PASS
read -p "Número do ramal (3 dígitos, ex: 002): " RAMAL
read -p "Nome da criança (ex: Pedro): " NOME

# --- Validações ---
if [[ ! "$RAMAL" =~ ^[0-9]{3}$ ]]; then
  echo -e "${RED}ERRO: Ramal deve ter 3 dígitos (ex: 002)${NC}"
  exit 1
fi

if [[ -z "$HT_IP" || -z "$HT_PASS" || -z "$NOME" ]]; then
  echo -e "${RED}ERRO: Todos os campos são obrigatórios${NC}"
  exit 1
fi

# --- Gera senha SIP forte ---
SIP_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
echo ""
echo -e "${GREEN}Senha SIP gerada: ${SIP_PASS}${NC}"

# --- Verifica conexão com o HT802 ---
echo ""
echo "[1/5] Conectando ao HT802 em ${HT_IP}..."
COOKIE_JAR="/tmp/gs_cookies_$$.txt"

# HT802V2 usa base64 na senha e campo P2 (não "password")
HT_PASS_B64=$(echo -n "${HT_PASS}" | base64)

LOGIN_RESP=$(curl -s -c "${COOKIE_JAR}" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d "username=admin&P2=${HT_PASS_B64}" \
  "http://${HT_IP}/cgi-bin/dologin" \
  --referer "http://${HT_IP}" \
  --connect-timeout 5 2>/dev/null || echo "FALHOU")

if echo "$LOGIN_RESP" | grep -q "FALHOU"; then
  echo -e "${RED}ERRO: Não consegui conectar ao HT802 em ${HT_IP}${NC}"
  rm -f "${COOKIE_JAR}"
  exit 1
fi

SID=$(echo "$LOGIN_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
body = data.get('body', {})
if isinstance(body, dict):
    print(body.get('session_token', body.get('sid', '')))
else:
    print('')
" 2>/dev/null || echo "")

if [[ -z "$SID" ]]; then
  echo -e "${RED}ERRO: Login falhou. Verifique a senha admin do HT802.${NC}"
  echo "Resposta: ${LOGIN_RESP}"
  rm -f "${COOKIE_JAR}"
  exit 1
fi

echo -e "${GREEN}✓ Login OK (session: ${SID:0:8}...)${NC}"

# --- Configura o HT802 ---
echo ""
echo "[2/5] Configurando HT802 (FXS PORT 1 = ramal ${RAMAL})..."

# P-values para FXS PORT 1:
# P271=1   Account Active = Yes
# P47      Primary SIP Server
# P35      SIP User ID
# P36      SIP Authenticate ID
# P34      SIP Authentication Password
# P3       Name (Display Name)
# P52=2    NAT Traversal = Keep-Alive
# P130=1   SIP Transport = TCP
# P31=1    SIP Registration = Yes
# P32=2    Register Expiration = 2 min (120 seg)
# P81=1    Unregister on Reboot = Yes

CONFIG_RESP=$(curl -s -b "${COOKIE_JAR}" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d "P271=1&P47=${VPS_IP}&P35=${RAMAL}&P36=${RAMAL}&P34=${SIP_PASS}&P3=${NOME}&P52=2&P130=1&P31=1&P32=2&P81=1&apply=1&session_token=${SID}" \
  "http://${HT_IP}/cgi-bin/api.values.post" \
  --referer "http://${HT_IP}" 2>/dev/null || echo "FALHOU")

if echo "$CONFIG_RESP" | grep -qi "success"; then
  echo -e "${GREEN}✓ HT802 configurado${NC}"
else
  echo -e "${YELLOW}Resposta do HT802: ${CONFIG_RESP}${NC}"
  echo "Continuando mesmo assim..."
fi

# --- Verifica se ramal já existe no servidor ---
echo ""
echo "[3/5] Adicionando ramal ${RAMAL} no servidor Asterisk..."

if [[ ! -f "$SSH_KEY" ]]; then
  echo -e "${RED}ERRO: Chave SSH não encontrada em ${SSH_KEY}${NC}"
  echo "Coloque a chave SSH no mesmo diretório deste script."
  rm -f "${COOKIE_JAR}"
  exit 1
fi

# Verifica se ramal já existe no pjsip_wizard.conf
RAMAL_EXISTS=$(ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} \
  "grep -c '^\[${RAMAL}\]' /etc/asterisk/pjsip_wizard.conf 2>/dev/null || echo 0")

SKIP_SERVER=0
if [[ "$RAMAL_EXISTS" -gt 0 ]]; then
  echo -e "${YELLOW}AVISO: Ramal ${RAMAL} já existe no servidor Asterisk.${NC}"
  read -p "Deseja sobrescrever a configuração existente? (s/n): " SOBRESCREVER
  if [[ "$SOBRESCREVER" != "s" && "$SOBRESCREVER" != "S" ]]; then
    echo "Pulando configuração do servidor."
    SKIP_SERVER=1
  fi
fi

if [[ "$SKIP_SERVER" -eq 0 ]]; then
  # Monta o bloco wizard
  WIZARD_BLOCK="; RAMAL ${RAMAL} — ${NOME}
[${RAMAL}]
type = wizard
accepts_registrations = yes
sends_registrations = no
accepts_auth = yes
remote_hosts = dynamic
inbound_auth/auth_type = userpass
inbound_auth/username = ${RAMAL}
inbound_auth/password = ${SIP_PASS}
endpoint/context = telefones-criancas
endpoint/allow = !all,ulaw,alaw
endpoint/direct_media = no
endpoint/rtp_symmetric = yes
endpoint/force_rport = yes
endpoint/rewrite_contact = yes
endpoint/callerid = ${NOME} <${RAMAL}>
aor/max_contacts = 1
aor/remove_existing = yes
aor/default_expiration = 120"

  # Remove entrada existente se houver
  ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} \
    "if grep -q '^\[${RAMAL}\]' /etc/asterisk/pjsip_wizard.conf 2>/dev/null; then
      echo 'Removendo entrada antiga do ramal ${RAMAL}...'
      sudo python3 -c \"
import re
with open('/etc/asterisk/pjsip_wizard.conf') as f:
    content = f.read()
content = re.sub(r'(\n; RAMAL ${RAMAL}[^\n]*\n|\n)\[${RAMAL}\]\n((?!\[)[^\n]*\n)*', '\n', content)
with open('/etc/asterisk/pjsip_wizard.conf', 'w') as f:
    f.write(content.strip() + '\n')
\"
    fi"

  # Adiciona nova entrada
  echo "$WIZARD_BLOCK" | ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} \
    "sudo tee -a /etc/asterisk/pjsip_wizard.conf > /dev/null"

  # Reinicia Asterisk (reload nao carrega secoes novas do wizard)
  ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} \
    "sudo systemctl restart asterisk && echo 'Asterisk reiniciado'"

  echo -e "${GREEN}✓ Ramal ${RAMAL} configurado no servidor${NC}"
else
  echo -e "${YELLOW}Servidor não modificado${NC}"
fi

# --- Cria device no portal web ---
echo ""
echo "[4/5] Criando device no portal web..."

# Verifica se device já existe no portal
DEVICE_INFO=$(ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} "
sudo /opt/telefone-portal/venv/bin/python3 -c \"
import sqlite3
conn = sqlite3.connect('/opt/telefone-portal/data/telefone.db')
row = conn.execute('SELECT registration_code, child_name, user_id FROM devices WHERE extension = ?', ('${RAMAL}',)).fetchone()
if row:
    status = 'ativado' if row[2] else 'nao_ativado'
    print(f'{row[0]}|{row[1]}|{status}')
else:
    print('NAO_EXISTE')
conn.close()
\"
")

if [[ "$DEVICE_INFO" != "NAO_EXISTE" ]]; then
  OLD_CODE=$(echo "$DEVICE_INFO" | cut -d'|' -f1)
  OLD_NAME=$(echo "$DEVICE_INFO" | cut -d'|' -f2)
  OLD_STATUS=$(echo "$DEVICE_INFO" | cut -d'|' -f3)

  echo -e "${YELLOW}AVISO: Device para ramal ${RAMAL} já existe no portal.${NC}"
  echo "  Nome: ${OLD_NAME}"
  echo "  Codigo: ${OLD_CODE}"
  echo "  Status: ${OLD_STATUS}"

  if [[ "$OLD_STATUS" == "ativado" ]]; then
    echo -e "${RED}Este device já está vinculado a um usuário!${NC}"
    read -p "Deseja desvinculá-lo e resetar? (s/n): " RESET_DEVICE
    if [[ "$RESET_DEVICE" == "s" || "$RESET_DEVICE" == "S" ]]; then
      REG_CODE=$(ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} "
sudo /opt/telefone-portal/venv/bin/python3 -c \"
import sqlite3, secrets, string
conn = sqlite3.connect('/opt/telefone-portal/data/telefone.db')
dev = conn.execute('SELECT id FROM devices WHERE extension = ?', ('${RAMAL}',)).fetchone()
dev_id = dev[0]
conn.execute('DELETE FROM schedules WHERE device_id = ?', (dev_id,))
conn.execute('DELETE FROM permissions WHERE device_id = ?', (dev_id,))
conn.execute('DELETE FROM permissions WHERE allowed_extension = ?', ('${RAMAL}',))
alphabet = string.ascii_uppercase + string.digits
code = ''.join(secrets.choice(alphabet) for _ in range(8))
conn.execute('UPDATE devices SET user_id = NULL, child_name = \\'\\', registration_code = ? WHERE id = ?', (code, dev_id))
conn.commit()
print(code)
conn.close()
\"
")
      echo -e "${GREEN}✓ Device resetado (novo codigo: ${REG_CODE})${NC}"
    else
      REG_CODE="$OLD_CODE"
      echo "Mantendo device existente."
    fi
  else
    read -p "Deseja gerar novo codigo de registro? (s/n): " NOVO_CODE
    if [[ "$NOVO_CODE" == "s" || "$NOVO_CODE" == "S" ]]; then
      REG_CODE=$(ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} "
sudo /opt/telefone-portal/venv/bin/python3 -c \"
import sqlite3, secrets, string
conn = sqlite3.connect('/opt/telefone-portal/data/telefone.db')
alphabet = string.ascii_uppercase + string.digits
code = ''.join(secrets.choice(alphabet) for _ in range(8))
conn.execute('UPDATE devices SET registration_code = ? WHERE extension = ?', (code, '${RAMAL}'))
conn.commit()
print(code)
conn.close()
\"
")
      echo -e "${GREEN}✓ Novo codigo gerado: ${REG_CODE}${NC}"
    else
      REG_CODE="$OLD_CODE"
      echo "Mantendo codigo existente: ${REG_CODE}"
    fi
  fi
else
  REG_CODE=$(ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} "
sudo /opt/telefone-portal/venv/bin/python3 -c \"
import sqlite3, secrets, string
conn = sqlite3.connect('/opt/telefone-portal/data/telefone.db')
alphabet = string.ascii_uppercase + string.digits
code = ''.join(secrets.choice(alphabet) for _ in range(8))
conn.execute('INSERT INTO devices (registration_code, extension, child_name) VALUES (?, ?, ?)', (code, '${RAMAL}', '${NOME}'))
conn.commit()
print(code)
conn.close()
\"
")
  echo -e "${GREEN}✓ Device criado no portal (codigo: ${REG_CODE})${NC}"
fi

# --- Reinicia o HT802 ---
echo ""
echo "[5/5] Reiniciando HT802..."

REBOOT_RESP=$(curl -s -b "${COOKIE_JAR}" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d "session_token=${SID}" \
  "http://${HT_IP}/cgi-bin/rs" \
  --referer "http://${HT_IP}" 2>/dev/null || echo "")

echo -e "${GREEN}✓ HT802 reiniciando${NC}"

# --- Salva credenciais ---
echo "" >> "${SCRIPT_DIR}/credenciais.md"
echo "| ${RAMAL}   | ${RAMAL}     | ${SIP_PASS} | HT802 - ${NOME} |" >> "${SCRIPT_DIR}/credenciais.md"

# --- Limpa ---
rm -f "${COOKIE_JAR}"

echo ""
echo "========================================="
echo -e "${GREEN} Configuração concluída!${NC}"
echo "========================================="
echo ""
echo "  Ramal:  ${RAMAL}"
echo "  Nome:   ${NOME}"
echo "  Senha SIP:  ${SIP_PASS}"
echo "  Codigo de registro: ${REG_CODE}"
echo ""
echo "  O HT802 vai reiniciar e se registrar automaticamente."
echo "  Aguarde ~1 minuto, depois teste:"
echo "    - Tire o telefone do gancho"
echo "    - Disque 100# para ouvir a hora"
echo ""
echo "  Para ativar no portal, acesse /ativar e use o codigo: ${REG_CODE}"
echo ""
echo -e "${YELLOW}IMPORTANTE para os pais:${NC}"
echo "  - Conectar o telefone na porta PHONE 1 (porta de cima)"
echo "  - Para ligar, discar o ramal + # (ex: 067#)"
echo ""
