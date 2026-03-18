#!/bin/bash
# =============================================================================
# firewall.sh — Configura iptables no VPS Oracle Cloud para o Asterisk
#
# Oracle Cloud usa iptables internamente ALÉM das Security Lists do painel web.
# É preciso liberar nos DOIS lugares.
#
# Uso: sudo bash firewall.sh
# =============================================================================

set -euo pipefail

echo "========================================="
echo " Configuração de Firewall (iptables)"
echo "========================================="

if [ "$EUID" -ne 0 ]; then
  echo "ERRO: Execute com sudo: sudo bash firewall.sh"
  exit 1
fi

# --- Libera SIP (sinalização) ---
echo "[1/3] Liberando SIP (porta 5060/UDP)..."
iptables -I INPUT 1 -p udp --dport 5060 -j ACCEPT

# --- Libera RTP (áudio das chamadas) ---
echo "[2/3] Liberando RTP (portas 10000-20000/UDP)..."
iptables -I INPUT 2 -p udp --dport 10000:20000 -j ACCEPT

# --- Salva regras para persistir após reboot ---
echo "[3/3] Salvando regras..."

# Oracle Cloud Ubuntu usa iptables-persistent ou netfilter-persistent
if command -v netfilter-persistent &> /dev/null; then
  netfilter-persistent save
elif [ -f /etc/iptables/rules.v4 ]; then
  iptables-save > /etc/iptables/rules.v4
else
  # Instala iptables-persistent para salvar regras
  echo "Instalando iptables-persistent..."
  DEBIAN_FRONTEND=noninteractive apt install -y iptables-persistent
  netfilter-persistent save
fi

echo ""
echo "========================================="
echo " Firewall configurado!"
echo "========================================="
echo ""
echo "Regras ativas:"
iptables -L INPUT -n --line-numbers | head -20
echo ""
echo "IMPORTANTE: Você TAMBÉM precisa liberar no painel da Oracle Cloud:"
echo "  Virtual Cloud Network → Security Lists → Ingress Rules:"
echo "  ┌─────────────┬──────────┬───────────────┬─────────────────────┐"
echo "  │ Source CIDR  │ Protocol │ Dest Port     │ Descrição           │"
echo "  ├─────────────┼──────────┼───────────────┼─────────────────────┤"
echo "  │ 0.0.0.0/0   │ UDP      │ 5060          │ SIP Signaling       │"
echo "  │ 0.0.0.0/0   │ UDP      │ 10000-20000   │ RTP Audio           │"
echo "  └─────────────┴──────────┴───────────────┴─────────────────────┘"
