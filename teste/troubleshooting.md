# Troubleshooting — Problemas Comuns e Soluções

## 1. Telefone sem tom de discagem

**Sintoma:** Tiro o telefone do gancho e não tem som nenhum.

**Verificar:**
- O cabo RJ11 está na porta FXS (não na porta PHONE do HT802)
- O HT802 está ligado (LED aceso)
- Tente outro cabo RJ11

---

## 2. Tem tom, mas ao discar não acontece nada

**Sintoma:** Tem tom de discagem mas ao discar 001 ou 067 fica mudo.

**Verificar no Asterisk:**
```bash
# Ver se o ramal está registrado
asterisk -rx 'pjsip show endpoints'

# Deve mostrar algo como:
#  Endpoint: 067    Available
#  Endpoint: 001    Available
```

**Se o ramal NÃO aparece como Available:**
- Verifique Primary SIP Server no HT802 (deve ser o IP do VPS)
- Verifique se SIP User ID, Authenticate ID e Password estão corretos
- Verifique se a porta 5060/UDP está aberta no firewall do VPS
- Teste conectividade: `ping IP_DO_VPS` de dentro da rede do HT802

**Se o ramal aparece como Available mas não toca:**
```bash
# Veja o log em tempo real enquanto tenta ligar
asterisk -rx 'core set verbose 5'
tail -f /var/log/asterisk/full
```

---

## 3. Liga, toca, mas sem áudio (um ou dois lados)

**Sintoma:** A chamada conecta, o telefone toca, mas não ouço nada (ou só um lado ouve).

**Causa mais provável:** Problema de NAT. O áudio (RTP) não está passando.

**Soluções:**
1. Verifique se as portas RTP (10000-20000/UDP) estão abertas no VPS
2. No HT802, verifique NAT Traversal = **Keep-Alive**
3. No Asterisk, adicione em `pjsip.conf` no endpoint:
   ```
   direct_media = no
   ```
   (Isso força o áudio a passar pelo servidor)

Para adicionar, edite cada endpoint no pjsip.conf:
```ini
[067]
type = endpoint
...
direct_media = no    ; <- adicionar esta linha
```

Depois recarregue:
```bash
asterisk -rx 'pjsip reload'
```

---

## 4. "Fora do horário" mas deveria estar funcionando

**Sintoma:** Ligação é rejeitada mesmo dentro do horário 8h-20h.

**Verificar:**
```bash
# Ver a hora do servidor
date

# Deve mostrar horário de Brasília (BRT, UTC-3)
# Se estiver errado:
sudo timedatectl set-timezone America/Sao_Paulo
```

---

## 5. Erro de registro: "401 Unauthorized"

**Sintoma:** HT802 não registra, log mostra 401.

**Verificar:**
- Senha no HT802 está exatamente igual ao `pjsip.conf`
- O campo "Authenticate ID" no HT802 está preenchido (igual ao SIP User ID)
- Cuidado com espaços extras ao copiar a senha

---

## 6. Dois HT802 na mesma rede e só um funciona

**Sintoma:** Só o primeiro HT802 registra, o segundo não.

**Causa:** Conflito de porta. Os dois estão tentando usar 5060.

**Solução:** Configure portas diferentes:
- HT802 #1: Local SIP Port = 5060, Local RTP Port = 10000
- HT802 #2: Local SIP Port = 5062, Local RTP Port = 10002

---

## 7. Chamada cai após ~30 segundos

**Sintoma:** A chamada conecta mas cai sozinha em ~30s.

**Causa provável:** Timeout de NAT no roteador.

**Soluções:**
- No HT802: NAT Traversal = **Keep-Alive**
- No HT802: Register Expiration = **120** (ou menor)
- Verifique se o roteador tem algum SIP ALG ativo — **desative o SIP ALG**
  (isso é uma das maiores causas de problema com VoIP doméstico)

**Como desativar SIP ALG:**
- Acesse a interface do roteador
- Procure em configurações avançadas / segurança / firewall
- Desative "SIP ALG" ou "SIP Application Layer Gateway"
- Cada roteador é diferente — procure pelo modelo específico

---

## 8. Comandos úteis do Asterisk

```bash
# Status dos ramais
asterisk -rx 'pjsip show endpoints'
asterisk -rx 'pjsip show registrations'

# Chamadas ativas
asterisk -rx 'core show channels'

# Recarregar configurações sem reiniciar
asterisk -rx 'dialplan reload'
asterisk -rx 'pjsip reload'

# Log em tempo real (verboso)
asterisk -rvvvvv

# Ver últimas chamadas
asterisk -rx 'cdr show status'

# Testar se um ramal está acessível
asterisk -rx 'pjsip show endpoint 067'
asterisk -rx 'pjsip show endpoint 001'

# Reiniciar Asterisk (último recurso)
sudo systemctl restart asterisk
```

---

## 9. Como ler o log do Asterisk

```bash
# Últimas 50 linhas
tail -n 50 /var/log/asterisk/full

# Acompanhar em tempo real
tail -f /var/log/asterisk/full

# Filtrar por um ramal específico
grep "067" /var/log/asterisk/full | tail -20
```
