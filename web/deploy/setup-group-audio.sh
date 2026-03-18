#!/bin/bash
# =============================================================================
# setup-group-audio.sh — Gera arquivos de audio em portugues para chamada em grupo
# Rodar no VPS apos instalar dependencias:
#   apt install espeak-ng sox
# =============================================================================

set -e

SOUNDS_DIR="/usr/share/asterisk/sounds/grupo"
mkdir -p "$SOUNDS_DIR"

echo "Gerando arquivos de audio para chamada em grupo..."

# Gerar audio com espeak-ng (disponivel em Ubuntu)
# "Entrando em chamada em grupo com N pessoas"
# N = 2, 3, 4 (maximo 5 participantes, entao quem entra ve no maximo 4 ja na sala)

generate() {
    local n=$1
    local texto=$2
    local tmpfile="/tmp/grupo-${n}.wav"
    local outfile="${SOUNDS_DIR}/entrando-${n}.wav"

    if command -v espeak-ng &>/dev/null; then
        espeak-ng -v pt-br -s 140 -w "$tmpfile" "$texto"
    elif command -v espeak &>/dev/null; then
        espeak -v pt-br -s 140 -w "$tmpfile" "$texto"
    else
        echo "ERRO: instale espeak-ng: apt install espeak-ng"
        exit 1
    fi

    # Converter para formato Asterisk (8kHz mono 16-bit PCM)
    if command -v sox &>/dev/null; then
        sox "$tmpfile" -r 8000 -c 1 -b 16 "$outfile"
    elif command -v ffmpeg &>/dev/null; then
        ffmpeg -y -i "$tmpfile" -ar 8000 -ac 1 -acodec pcm_s16le "$outfile" 2>/dev/null
    else
        echo "AVISO: sem sox ou ffmpeg, usando arquivo original"
        cp "$tmpfile" "$outfile"
    fi

    rm -f "$tmpfile"
    echo "  Criado: $outfile"
}

generate 2 "Entrando em chamada em grupo com duas pessoas"
generate 3 "Entrando em chamada em grupo com três pessoas"
generate 4 "Entrando em chamada em grupo com quatro pessoas"

# Ajustar permissoes para o Asterisk
chown -R asterisk:asterisk "$SOUNDS_DIR"
chmod 644 "$SOUNDS_DIR"/*.wav

echo ""
echo "Arquivos de audio criados em $SOUNDS_DIR"
ls -la "$SOUNDS_DIR"
