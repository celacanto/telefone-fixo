#!/bin/bash
# =============================================================================
# setup-vps.sh — Instala e configura o Asterisk no VPS Oracle Cloud (Ubuntu)
# Projeto: Telefone para crianças via internet
#
# Uso: sudo bash setup-vps.sh
# =============================================================================

set -euo pipefail

echo "========================================="
echo " Instalação do Asterisk - Telefone Fixo"
echo "========================================="

# --- Verifica se está rodando como root ---
if [ "$EUID" -ne 0 ]; then
  echo "ERRO: Execute com sudo: sudo bash setup-vps.sh"
  exit 1
fi

# --- Configura timezone para São Paulo ---
echo "[1/7] Configurando timezone para America/Sao_Paulo..."
timedatectl set-timezone America/Sao_Paulo

# --- Atualiza o sistema ---
echo "[2/7] Atualizando sistema..."
apt update && apt upgrade -y

# --- Instala Asterisk e dependências ---
echo "[3/7] Instalando Asterisk..."
apt install -y asterisk asterisk-core-sounds-pt-br

# --- Backup das configs originais ---
echo "[4/7] Fazendo backup das configs originais..."
BACKUP_DIR="/etc/asterisk/backup-original"
mkdir -p "$BACKUP_DIR"
for f in pjsip.conf extensions.conf modules.conf; do
  if [ -f "/etc/asterisk/$f" ]; then
    cp "/etc/asterisk/$f" "$BACKUP_DIR/$f.bak"
  fi
done

# --- Copia configs do projeto ---
echo "[5/7] Instalando configurações do projeto..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/pjsip.conf" /etc/asterisk/pjsip.conf
cp "$SCRIPT_DIR/extensions.conf" /etc/asterisk/extensions.conf

# Garante que o Asterisk é dono dos arquivos
chown asterisk:asterisk /etc/asterisk/pjsip.conf /etc/asterisk/extensions.conf
chmod 640 /etc/asterisk/pjsip.conf /etc/asterisk/extensions.conf

# --- Configura modules.conf para carregar PJSIP ---
echo "[6/7] Configurando módulos..."
cat > /etc/asterisk/modules.conf << 'MODEOF'
[modules]
autoload = yes

; Desabilita chan_sip antigo (usamos PJSIP)
noload = chan_sip.so

; Garante que PJSIP está carregado
load = res_pjsip.so
load = res_pjsip_transport_udp.so
load = res_pjsip_authenticator_digest.so
load = res_pjsip_endpoint_identifier_user.so
load = res_pjsip_registrar.so
load = res_pjsip_session.so
load = chan_pjsip.so
MODEOF

chown asterisk:asterisk /etc/asterisk/modules.conf

# --- Habilita e reinicia o Asterisk ---
echo "[7/7] Habilitando e reiniciando Asterisk..."
systemctl enable asterisk
systemctl restart asterisk

# --- Verifica se está rodando ---
echo ""
echo "========================================="
echo " Verificação"
echo "========================================="

if systemctl is-active --quiet asterisk; then
  echo "✓ Asterisk está RODANDO"
else
  echo "✗ Asterisk NÃO está rodando. Verifique: journalctl -u asterisk -n 50"
  exit 1
fi

# Verifica se PJSIP está escutando
sleep 2
if ss -ulnp | grep -q ":5060"; then
  echo "✓ PJSIP está escutando na porta 5060/UDP"
else
  echo "✗ PJSIP NÃO está na porta 5060. Verifique: asterisk -rx 'pjsip show transports'"
fi

echo ""
echo "========================================="
echo " Instalação concluída!"
echo "========================================="
echo ""
echo "Próximos passos:"
echo "  1. Execute o firewall.sh: sudo bash firewall.sh"
echo "  2. Configure as Security Lists na Oracle Cloud (ver checklist)"
echo "  3. Configure os HT802 (ver grandstream/checklist-ht802.md)"
echo ""
echo "Comandos úteis:"
echo "  asterisk -rx 'pjsip show endpoints'     — ver ramais"
echo "  asterisk -rx 'pjsip show registrations'  — ver registros"
echo "  asterisk -rx 'core show channels'        — chamadas ativas"
echo "  tail -f /var/log/asterisk/full            — log em tempo real"
