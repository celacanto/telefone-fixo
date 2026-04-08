#!/bin/bash
# =============================================================================
# limpar-ramal.sh — Remove completamente um ramal de teste do sistema
#
# Uso: bash limpar-ramal.sh [RAMAL]
#
# Remove:
#   - Device, user (se sem outros devices), permissions, schedules, call_logs
#   - Ramal do pjsip_wizard.conf no Asterisk
#   - Dados residuais no AstDB (conferencias, registros)
#
# Util para limpar ramais de teste antes de reconfigurar o aparelho para envio.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -f "$SCRIPT_DIR/.env" ]]; then
  source "$SCRIPT_DIR/.env"
else
  echo "Erro: arquivo .env não encontrado em $SCRIPT_DIR"
  exit 1
fi

VPS_IP="${TELEFONE_VPS_IP:?Defina TELEFONE_VPS_IP no .env}"
SSH_KEY="$SCRIPT_DIR/${TELEFONE_SSH_KEY:?Defina TELEFONE_SSH_KEY no .env}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# --- Pede ramal ---
if [[ -n "${1:-}" ]]; then
  RAMAL="$1"
else
  read -p "Numero do ramal para limpar (ex: 005): " RAMAL
fi

if [[ ! "$RAMAL" =~ ^[0-9]{3}$ ]]; then
  echo -e "${RED}ERRO: Ramal deve ter 3 digitos${NC}"
  exit 1
fi

SSH_CMD="ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no ubuntu@${VPS_IP}"

# --- Mostra o que sera removido ---
echo ""
echo "==========================================="
echo " Limpar ramal ${RAMAL}"
echo "==========================================="
echo ""

echo "[1/4] Verificando o que existe para o ramal ${RAMAL}..."

INFO=$(${SSH_CMD} "sudo python3 -c '
import sqlite3, json
conn = sqlite3.connect(\"/opt/telefone-portal/data/telefone.db\")
conn.row_factory = sqlite3.Row
info = {}

dev = conn.execute(\"SELECT * FROM devices WHERE extension = ?\", (\"${RAMAL}\",)).fetchone()
if dev:
    info[\"device\"] = dict(dev)
    uid = dev[\"user_id\"]
    if uid:
        user = conn.execute(\"SELECT id, email, name FROM users WHERE id = ?\", (uid,)).fetchone()
        if user:
            info[\"user\"] = dict(user)
            other_devices = conn.execute(\"SELECT COUNT(*) as c FROM devices WHERE user_id = ? AND extension != ?\", (uid, \"${RAMAL}\")).fetchone()[\"c\"]
            info[\"user_other_devices\"] = other_devices

perms = conn.execute(\"SELECT COUNT(*) as c FROM permissions WHERE device_id IN (SELECT id FROM devices WHERE extension = ?) OR allowed_extension = ?\", (\"${RAMAL}\",\"${RAMAL}\")).fetchone()[\"c\"]
info[\"permissions\"] = perms

scheds = conn.execute(\"SELECT COUNT(*) as c FROM schedules WHERE device_id IN (SELECT id FROM devices WHERE extension = ?)\", (\"${RAMAL}\",)).fetchone()[\"c\"]
info[\"schedules\"] = scheds

logs = conn.execute(\"SELECT COUNT(*) as c FROM call_logs WHERE caller_ext = ? OR callee_ext = ?\", (\"${RAMAL}\",\"${RAMAL}\")).fetchone()[\"c\"]
info[\"call_logs\"] = logs

conn.close()
print(json.dumps(info))
'" 2>/dev/null)

ASTERISK_EXISTS=$(${SSH_CMD} "sudo grep -c '^\[${RAMAL}\]' /etc/asterisk/pjsip_wizard.conf 2>/dev/null || echo 0")

# Parse e mostra
HAS_SOMETHING=0

if echo "$INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'device' in d else 1)" 2>/dev/null; then
  CHILD_NAME=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['device'].get('child_name','?'))")
  echo -e "  Device: ramal ${RAMAL} (${CHILD_NAME})"
  HAS_SOMETHING=1
else
  echo -e "  Device: ${YELLOW}nao encontrado no portal${NC}"
fi

if echo "$INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'user' in d else 1)" 2>/dev/null; then
  USER_NAME=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['user'].get('name','?'))")
  USER_EMAIL=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['user'].get('email','?'))")
  OTHER_DEVS=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('user_other_devices',0))")
  if [[ "$OTHER_DEVS" -gt 0 ]]; then
    echo -e "  User: ${USER_NAME} (${USER_EMAIL}) — ${YELLOW}tem ${OTHER_DEVS} outro(s) device(s), so desvincula${NC}"
  else
    echo -e "  User: ${USER_NAME} (${USER_EMAIL}) — sera removido"
  fi
  HAS_SOMETHING=1
fi

PERMS=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('permissions',0))")
SCHEDS=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('schedules',0))")
LOGS=$(echo "$INFO" | python3 -c "import sys,json; print(json.load(sys.stdin).get('call_logs',0))")

[[ "$PERMS" -gt 0 ]] && echo "  Permissions: ${PERMS}" && HAS_SOMETHING=1
[[ "$SCHEDS" -gt 0 ]] && echo "  Schedules: ${SCHEDS}" && HAS_SOMETHING=1
[[ "$LOGS" -gt 0 ]] && echo "  Call logs: ${LOGS}" && HAS_SOMETHING=1

if [[ "$ASTERISK_EXISTS" -gt 0 ]]; then
  echo "  Asterisk: ramal configurado no pjsip_wizard.conf"
  HAS_SOMETHING=1
else
  echo -e "  Asterisk: ${YELLOW}nao encontrado${NC}"
fi

if [[ "$HAS_SOMETHING" -eq 0 ]]; then
  echo -e "\n${YELLOW}Nada encontrado para o ramal ${RAMAL}.${NC}"
  exit 0
fi

# --- Confirmacao ---
echo ""
read -p "Confirma a remocao completa do ramal ${RAMAL}? (s/n): " CONFIRM
if [[ "$CONFIRM" != "s" && "$CONFIRM" != "S" ]]; then
  echo "Cancelado."
  exit 0
fi

# --- Limpa portal ---
echo ""
echo "[2/4] Limpando portal..."

${SSH_CMD} "sudo python3 -c '
import sqlite3
conn = sqlite3.connect(\"/opt/telefone-portal/data/telefone.db\")

dev = conn.execute(\"SELECT id, user_id FROM devices WHERE extension = ?\", (\"${RAMAL}\",)).fetchone()
if dev:
    dev_id, user_id = dev

    conn.execute(\"DELETE FROM permissions WHERE device_id = ? OR allowed_extension = ?\", (dev_id, \"${RAMAL}\"))
    conn.execute(\"DELETE FROM schedules WHERE device_id = ?\", (dev_id,))
    conn.execute(\"DELETE FROM call_logs WHERE caller_ext = ? OR callee_ext = ?\", (\"${RAMAL}\", \"${RAMAL}\"))
    conn.execute(\"DELETE FROM devices WHERE id = ?\", (dev_id,))

    if user_id:
        remaining = conn.execute(\"SELECT COUNT(*) FROM devices WHERE user_id = ?\", (user_id,)).fetchone()[0]
        if remaining == 0:
            conn.execute(\"DELETE FROM users WHERE id = ?\", (user_id,))
            print(\"  User removido (sem outros devices)\")
        else:
            print(f\"  User mantido ({remaining} device(s) restante(s))\")

    conn.commit()
    print(\"  Device, permissions, schedules e call_logs removidos\")
else:
    print(\"  Nenhum device no portal\")

conn.close()
'" 2>/dev/null

echo -e "${GREEN}  Portal limpo${NC}"

# --- Limpa Asterisk ---
echo ""
echo "[3/4] Limpando Asterisk..."

if [[ "$ASTERISK_EXISTS" -gt 0 ]]; then
  ${SSH_CMD} "
    sudo python3 -c '
import re
with open(\"/etc/asterisk/pjsip_wizard.conf\") as f:
    content = f.read()
content = re.sub(r\"\n?\[${RAMAL}\]\n(?:(?!\[).)*\", \"\", content, flags=re.DOTALL)
with open(\"/etc/asterisk/pjsip_wizard.conf\", \"w\") as f:
    f.write(content)
print(\"  Secao [${RAMAL}] removida do pjsip_wizard.conf\")
'
    sudo asterisk -rx 'database deltree registrar/contact/${RAMAL}' 2>/dev/null || true
    sudo asterisk -rx 'database del confbridge ${RAMAL}' 2>/dev/null || true
    sudo systemctl restart asterisk 2>&1
  " 2>/dev/null
  echo -e "${GREEN}  Asterisk limpo e reiniciado${NC}"
else
  echo "  Nada para limpar no Asterisk"
fi

# --- Verificacao final ---
echo ""
echo "[4/4] Verificacao final..."

RESULT=$(${SSH_CMD} "
sudo python3 -c '
import sqlite3
conn = sqlite3.connect(\"/opt/telefone-portal/data/telefone.db\")
d = conn.execute(\"SELECT COUNT(*) FROM devices WHERE extension = ?\", (\"${RAMAL}\",)).fetchone()[0]
p = conn.execute(\"SELECT COUNT(*) FROM permissions WHERE device_id IN (SELECT id FROM devices WHERE extension = ?) OR allowed_extension = ?\", (\"${RAMAL}\",\"${RAMAL}\")).fetchone()[0]
c = conn.execute(\"SELECT COUNT(*) FROM call_logs WHERE caller_ext = ? OR callee_ext = ?\", (\"${RAMAL}\",\"${RAMAL}\")).fetchone()[0]
conn.close()
print(f\"{d+p+c}\")
'
sudo grep -c '^\[${RAMAL}\]' /etc/asterisk/pjsip_wizard.conf 2>/dev/null || echo 0
" 2>/dev/null)

PORTAL_COUNT=$(echo "$RESULT" | head -1)
ASTERISK_COUNT=$(echo "$RESULT" | tail -1)

if [[ "$PORTAL_COUNT" -eq 0 && "$ASTERISK_COUNT" -eq 0 ]]; then
  echo -e "${GREEN}Ramal ${RAMAL} completamente removido do sistema.${NC}"
else
  echo -e "${RED}AVISO: Ainda restam dados (portal=${PORTAL_COUNT}, asterisk=${ASTERISK_COUNT})${NC}"
fi

echo ""
echo "O aparelho pode ser reconfigurado com: bash configurar-telefone.sh"
