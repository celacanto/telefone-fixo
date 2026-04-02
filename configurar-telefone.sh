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
#   5. Aguardar e confirmar registro SIP no servidor
# =============================================================================

set -euo pipefail

# --- Configurações fixas ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Carrega .env do mesmo diretório do script
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  source "$SCRIPT_DIR/.env"
else
  echo "Erro: arquivo .env não encontrado em $SCRIPT_DIR"
  echo "Crie um .env com: TELEFONE_VPS_IP e TELEFONE_SSH_KEY"
  exit 1
fi

VPS_IP="${TELEFONE_VPS_IP:?Defina TELEFONE_VPS_IP no .env}"
SSH_KEY="$SCRIPT_DIR/${TELEFONE_SSH_KEY:?Defina TELEFONE_SSH_KEY no .env}"

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

# --- Helper Python para HTTP do HT802 (firmware antigo tem headers malformados) ---
GS_HELPER="/tmp/gs_helper_$$.py"
cat > "${GS_HELPER}" << 'PYHELPER'
#!/usr/bin/env python3
"""Helper para comunicação HTTP com Grandstream HT802/HT801 (firmware antigo e V2).

O firmware antigo retorna headers HTTP duplicados/malformados que curl e urllib rejeitam.
Este helper usa socket raw para parsear a resposta manualmente.
"""
import socket, sys, re, json, urllib.parse

def http_post(ip, path, body, cookie=None, timeout=10):
    """Faz POST via socket raw. Retorna (headers_dict, body_text, raw_headers)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, 80))
    except (socket.timeout, ConnectionRefusedError, OSError):
        return None, None, None

    headers = f"POST {path} HTTP/1.1\r\nHost: {ip}\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: {len(body)}\r\nConnection: close\r\n"
    if cookie:
        headers += f"Cookie: session_id={cookie}\r\n"
    headers += "\r\n"
    s.sendall((headers + body).encode())

    resp = b''
    while True:
        try:
            chunk = s.recv(8192)
            if not chunk:
                break
            resp += chunk
        except:
            break
    s.close()

    text = resp.decode('utf-8', errors='replace')
    # Separar headers do body (procura <html ou duplo newline)
    html_idx = text.lower().find('<html')
    if html_idx > 0:
        raw_h = text[:html_idx]
        body_text = text[html_idx:]
    else:
        parts = re.split(r'\r?\n\r?\n', text, maxsplit=1)
        raw_h = parts[0] if len(parts) > 1 else ''
        body_text = parts[1] if len(parts) > 1 else text

    # Parse headers
    hdict = {}
    for line in raw_h.split('\n'):
        if ':' in line and not line.startswith('HTTP'):
            k, v = line.split(':', 1)
            hdict[k.strip().lower()] = v.strip()
    return hdict, body_text, raw_h

def http_get(ip, path, cookie=None, timeout=10):
    """Faz GET via socket raw."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, 80))
    except:
        return None, None
    headers = f"GET {path} HTTP/1.1\r\nHost: {ip}\r\nConnection: close\r\n"
    if cookie:
        headers += f"Cookie: session_id={cookie}\r\n"
    headers += "\r\n"
    s.sendall(headers.encode())
    resp = b''
    while True:
        try:
            chunk = s.recv(8192)
            if not chunk:
                break
            resp += chunk
        except:
            break
    s.close()
    text = resp.decode('utf-8', errors='replace')
    html_idx = text.lower().find('<html')
    return text[html_idx:] if html_idx >= 0 else text, text[:html_idx] if html_idx >= 0 else ''

cmd = sys.argv[1]
ip = sys.argv[2]

if cmd == "detect":
    # Testa se é HT802V2 (Vue.js) ou legacy pela página de login (sem gastar tentativa)
    body, _ = http_get(ip, "/cgi-bin/login", timeout=5)
    if body is None:
        print("UNREACHABLE")
    elif "vue" in body.lower() or "api.values" in body or "XMLHttpRequest" in body:
        print("v2")
    elif "gnkey" in body or "Grandstream" in body:
        print("legacy")
    else:
        # Fallback: tenta pelo content-type da resposta de login
        print("legacy")

elif cmd == "login":
    password = sys.argv[3]
    firmware = sys.argv[4]  # "v2" ou "legacy"

    if firmware == "v2":
        import base64
        pwd_b64 = base64.b64encode(password.encode()).decode()
        _, body, _ = http_post(ip, "/cgi-bin/dologin",
            f"username=admin&P2={pwd_b64}",
            timeout=10)
        if body is None:
            print("ERROR:connection")
            sys.exit(1)
        try:
            data = json.loads(body.strip())
            b = data.get('body', {})
            sid = b.get('session_token', b.get('sid', '')) if isinstance(b, dict) else ''
            if sid:
                print(f"OK:{sid}")
            else:
                print("ERROR:auth")
        except:
            print("ERROR:parse")
    else:
        # Legacy: precisa do session_token da página admin para obter sessão privilegiada
        # 1. GET /cgi-bin/update retorna página de admin login com session_token
        admin_page, _ = http_get(ip, "/cgi-bin/update", timeout=5)
        session_token = ""
        if admin_page:
            m = re.search(r'name="session_token"[^>]*value="([^"]+)"', admin_page)
            if m:
                session_token = m.group(1)

        # 2. POST /cgi-bin/dologin com session_token para obter sessão admin
        params = {"username": "admin", "P2": password, "Login": "Login"}
        if session_token:
            params["session_token"] = session_token

        body = urllib.parse.urlencode(params)
        hdrs, resp_body, _ = http_post(ip, "/cgi-bin/dologin", body, timeout=10)
        if hdrs is None:
            print("ERROR:connection")
            sys.exit(1)

        if resp_body and "locked" in resp_body.lower():
            print("ERROR:locked")
            sys.exit(1)

        # Extrair session_id do Set-Cookie header
        cookie_h = hdrs.get('set-cookie', '')
        m = re.search(r'session_id=([^;\s]+)', cookie_h)
        if m:
            sid = m.group(1)
            # Verificar se realmente logou (resposta deve ter STATUS/config)
            if "STATUS" in (resp_body or '') or "FXS" in (resp_body or '') or "BASIC" in (resp_body or ''):
                print(f"OK:{sid}")
            else:
                print("ERROR:auth")
        else:
            print("ERROR:auth")

elif cmd == "config":
    sid = sys.argv[3]
    firmware = sys.argv[4]
    pvalues = sys.argv[5]  # URL-encoded P-values

    if firmware == "v2":
        _, body, _ = http_post(ip, "/cgi-bin/api.values.post",
            f"{pvalues}&apply=1&session_token={sid}", timeout=10)
        if body and "success" in body.lower():
            print("OK")
        else:
            print(f"WARN:{(body or '')[:200]}")
    else:
        # Legacy: precisa do session_token e gnkey do form da página config_a1
        config_page, _ = http_get(ip, "/cgi-bin/config_a1", cookie=sid, timeout=10)
        form_token = ""
        form_gnkey = "0b82"
        if config_page:
            m = re.search(r'name="session_token"[^>]*value="([^"]+)"', config_page)
            if m:
                form_token = m.group(1)
            m = re.search(r'name="gnkey"[^>]*value=([^\s>]+)', config_page)
            if m:
                form_gnkey = m.group(1).strip('"')

        update_body = f"{pvalues}&session_token={form_token}&gnkey={form_gnkey}&update=Update"
        _, body, _ = http_post(ip, "/cgi-bin/update", update_body, cookie=sid, timeout=10)
        if body is None:
            print("ERROR:connection")
        elif "doadminlogin" in (body or ''):
            print("ERROR:session")
        else:
            print("OK")

elif cmd == "reboot":
    sid = sys.argv[3]
    firmware = sys.argv[4]
    if firmware == "v2":
        http_post(ip, "/cgi-bin/rs", f"session_token={sid}", timeout=5)
    else:
        # Legacy: precisa de session_token do form para reboot
        config_page, _ = http_get(ip, "/cgi-bin/config_a1", cookie=sid, timeout=5)
        form_token = ""
        if config_page:
            m = re.search(r'name="session_token"[^>]*value="([^"]+)"', config_page)
            if m:
                form_token = m.group(1)
        http_post(ip, "/cgi-bin/rs", f"session_token={form_token}", cookie=sid, timeout=5)
    print("OK")
PYHELPER

# --- Verifica conexão e senha do HT802 ---
echo ""
COOKIE_JAR="/tmp/gs_cookies_$$.txt"
MAX_TENTATIVAS=3
TENTATIVA=0
SID=""
HT_FIRMWARE=""

echo "[1/6] Conectando ao HT802 em ${HT_IP}..."

# Detecta tipo de firmware
HT_FIRMWARE=$(python3 "${GS_HELPER}" detect "${HT_IP}")
if [[ "$HT_FIRMWARE" == "UNREACHABLE" ]]; then
  echo -e "${RED}ERRO: Não consegui conectar ao HT802 em ${HT_IP}${NC}"
  echo "  Verifique se o IP está correto e o HT802 está ligado."
  rm -f "${GS_HELPER}"
  exit 1
fi
echo "  Firmware detectado: ${HT_FIRMWARE}"

# Login
while [[ -z "$SID" ]]; do
  TENTATIVA=$((TENTATIVA + 1))

  LOGIN_RESULT=$(python3 "${GS_HELPER}" login "${HT_IP}" "${HT_PASS}" "${HT_FIRMWARE}")

  if [[ "$LOGIN_RESULT" == OK:* ]]; then
    SID="${LOGIN_RESULT#OK:}"
    break
  elif [[ "$LOGIN_RESULT" == "ERROR:locked" ]]; then
    echo -e "${RED}ERRO: HT802 bloqueado por excesso de tentativas de login.${NC}"
    echo -e "${YELLOW}Desliga o HT802 da tomada, espera 10 segundos, liga de novo e tenta de novo.${NC}"
    rm -f "${GS_HELPER}"
    exit 1
  elif [[ "$LOGIN_RESULT" == "ERROR:connection" ]]; then
    echo -e "${RED}ERRO: Não consegui conectar ao HT802 em ${HT_IP}${NC}"
    rm -f "${GS_HELPER}"
    exit 1
  else
    # Senha incorreta
    if [[ $TENTATIVA -ge $MAX_TENTATIVAS ]]; then
      echo -e "${RED}ERRO: Senha incorreta apos ${MAX_TENTATIVAS} tentativas.${NC}"
      echo -e "${YELLOW}Dica: Tente fazer factory reset (botao RESET por 7s) e use 'admin' ou o MAC em minusculas como senha.${NC}"
      rm -f "${GS_HELPER}"
      exit 1
    fi
    echo -e "${RED}Senha incorreta. Tentativa ${TENTATIVA}/${MAX_TENTATIVAS}.${NC}"
    read -p "Digite a senha admin novamente: " HT_PASS
  fi
done

echo -e "${GREEN}✓ Login OK — firmware ${HT_FIRMWARE} (session: ${SID:0:8}...)${NC}"

# --- Configura o HT802 ---
echo ""
echo "[2/6] Configurando HT802 (FXS PORT 1 = ramal ${RAMAL})..."

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
# --- Audio quality ---
# P57=9    Preferred Vocoder 1 = G.722 (wideband HD)
# P58=0    Preferred Vocoder 2 = PCMU (fallback)
# P59=8    Preferred Vocoder 3 = PCMA (fallback)
# P133=1   Jitter Buffer Type = Adaptive
# P132=1   Jitter Buffer Length = Medium
# P50=0    VAD/Silence Suppression = Disabled (evita corte de fala)
# P824=0   Line Echo Canceller = Enabled (0 = enabled, campo "Disable")
# P4441=0  Network Echo Suppressor = Enabled
# P291=1   Symmetric RTP = Yes

PVALUES="P271=1&P47=${VPS_IP}&P35=${RAMAL}&P36=${RAMAL}&P34=${SIP_PASS}&P3=${NOME}&P52=2&P130=1&P31=1&P32=2&P81=1&P57=9&P58=0&P59=8&P133=1&P132=1&P50=0&P824=0&P4441=0&P291=1"

CONFIG_RESULT=$(python3 "${GS_HELPER}" config "${HT_IP}" "${SID}" "${HT_FIRMWARE}" "${PVALUES}")

if [[ "$CONFIG_RESULT" == OK* ]]; then
  echo -e "${GREEN}✓ HT802 configurado${NC}"
elif [[ "$CONFIG_RESULT" == ERROR:session ]]; then
  echo -e "${RED}ERRO: Sessão expirou durante configuração${NC}"
  echo "Continuando mesmo assim..."
else
  echo -e "${YELLOW}Resposta: ${CONFIG_RESULT}${NC}"
  echo "Continuando mesmo assim..."
fi

# --- Verifica se ramal já existe no servidor ---
echo ""
echo "[3/6] Adicionando ramal ${RAMAL} no servidor Asterisk..."

if [[ ! -f "$SSH_KEY" ]]; then
  echo -e "${RED}ERRO: Chave SSH não encontrada em ${SSH_KEY}${NC}"
  echo "Coloque a chave SSH no mesmo diretório deste script."
  rm -f "${COOKIE_JAR}" "${GS_HELPER}"
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
endpoint/allow = !all,g722,ulaw,alaw
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
echo "[4/6] Criando device no portal web..."

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
echo "[5/6] Reiniciando HT802..."

python3 "${GS_HELPER}" reboot "${HT_IP}" "${SID}" "${HT_FIRMWARE}" 2>/dev/null || true

echo -e "${GREEN}✓ HT802 reiniciando${NC}"

# --- Aguarda registro SIP ---
echo ""
echo "[6/6] Aguardando ramal ${RAMAL} registrar no servidor..."
echo "      (timeout: 120 segundos)"

REGISTERED=0
for i in $(seq 1 24); do
  sleep 5
  CONTACT=$(ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no ubuntu@${VPS_IP} \
    "sudo asterisk -rx 'pjsip show contacts' 2>/dev/null" | grep "^  Contact:  ${RAMAL}/" | grep -v "sip:dynamic" || true)
  if [[ -n "$CONTACT" ]]; then
    REGISTERED=1
    break
  fi
  printf "  %3ds...\r" $((i * 5))
done
echo ""

if [[ "$REGISTERED" -eq 1 ]]; then
  echo -e "${GREEN}✓ Ramal ${RAMAL} registrado no servidor com sucesso!${NC}"
else
  echo -e "${RED}AVISO: Ramal ${RAMAL} NÃO registrou após 120 segundos.${NC}"
  echo "  Verifique:"
  echo "    - O telefone está na porta PHONE 1 (porta de cima)?"
  echo "    - O HT802 tem acesso à internet?"
  echo "    - Tente reiniciar o HT802 (tirar da tomada e religar)"
fi

# --- Salva credenciais ---
echo "" >> "${SCRIPT_DIR}/credenciais.md"
echo "| ${RAMAL}   | ${RAMAL}     | ${SIP_PASS} | HT802 - ${NOME} |" >> "${SCRIPT_DIR}/credenciais.md"

# --- Limpa ---
rm -f "${COOKIE_JAR}" "${GS_HELPER}"

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
echo "  Teste: tire o telefone do gancho e disque 100# para ouvir a hora."
echo ""
echo "  Para ativar no portal, acesse /ativar e use o codigo: ${REG_CODE}"
echo ""
echo -e "${YELLOW}IMPORTANTE para os pais:${NC}"
echo "  - Conectar o telefone na porta PHONE 1 (porta de cima)"
echo "  - Para ligar, discar o ramal + # (ex: 067#)"
echo ""
