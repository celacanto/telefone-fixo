# CLAUDE.md — Telefone Fixo para Criancas

## O que e este projeto

Sistema de telefonia VoIP para criancas ligarem umas para as outras usando telefones
com fio (analogicos) + adaptadores Grandstream HT802V2/HT801 + servidor Asterisk na nuvem.
Cada crianca tem um ramal (ex: 067, 001) e pode ligar para as outras discando o numero + #.
Totalmente gratuito: Oracle Cloud Free Tier + Asterisk open-source.

## Arquitetura

```
[Celular do Pai] --HTTPS--> [nginx :443] --> [Flask :5000] --> [SQLite]
                                                                   ^
[Telefone] --> [HT802] --SIP/TCP--> [Asterisk] --AGI--> [check_call.py le SQLite]
                                                    \--> [log_call.py loga duracao]
```

- **Aparelhos**: Grandstream HT802V2 ou HT801 (ATA — converte telefone analogico em VoIP)
- **Servidor**: Asterisk PBX em Oracle Cloud Free Tier (VM.Standard.E2.1.Micro, Ubuntu)
- **Portal Web**: Flask + SQLite + nginx no mesmo VPS
- **HTTPS**: https://telefone-fixo.duckdns.org (DuckDNS + Let's Encrypt)
- **Transporte SIP**: TCP (NAO UDP — SIP ALG dos roteadores domesticos corrompe UDP)
- **IP do VPS**: 163.176.157.229
- **SSH**: `ssh -i ssh-key-2026-03-02.key ubuntu@163.176.157.229`

## Ramais ativos

| Ramal | Nome         | Aparelho | Familia     | Status |
|-------|--------------|----------|-------------|--------|
| 067   | Inacio       | HT802V2  | Daniel      | Ativo  |
| 001   | Mada e Vio   | HT801    | Victor      | Ativo  |

## Estrutura de arquivos

```
telefone_fixo/
  CLAUDE.md                      <-- Este arquivo
  configurar-telefone.sh         <-- Script automatico: configura HT802 + servidor + portal
  credenciais.md                 <-- Senhas SIP e dados de acesso (SENSIVEL)
  ssh-key-2026-03-02.key         <-- Chave SSH do VPS Oracle Cloud
  servidor/
    pjsip.conf                   <-- Transportes SIP (UDP+TCP) — copia LOCAL DESATUALIZADA
    pjsip_wizard.conf            <-- Definicao dos ramais — copia LOCAL DESATUALIZADA
    extensions.conf              <-- Dialplan antigo — copia LOCAL DESATUALIZADA
    setup-vps.sh                 <-- Script de instalacao inicial do Asterisk
    firewall.sh                  <-- Regras iptables (falta TCP 5060 — ver nota)
  grandstream/
    checklist-ht802.md           <-- Guia de configuracao manual do HT802
  expansao/
    novo-telefone.md             <-- Instrucoes para adicionar telefone (DESATUALIZADO)
  teste/
    troubleshooting.md           <-- Guia de resolucao de problemas
  web/
    app.py                       <-- Flask app principal (rotas, auth, CRUD)
    models.py                    <-- Schema SQLite + helpers de consulta
    config.py                    <-- Configuracoes (SECRET_KEY, DB_PATH)
    requirements.txt             <-- Dependencias Python (Flask, pytz)
    migrate.py                   <-- Script de migracao dos dados existentes
    templates/
      base.html                  <-- Layout base: navbar escura + tabs sticky
      login.html                 <-- Tela de login
      activate.html              <-- Ativacao: codigo + email + nome da crianca
      verify_email.html          <-- Verificacao email: codigo de 6 digitos
      dashboard.html             <-- Lista de aparelhos (so se tiver mais de 1)
      devices.html               <-- Vincular novo aparelho
      schedule.html              <-- Horarios permitidos: cards com toggle + selects 24h
      contacts.html              <-- Contatos: cards com status colorido
      call_logs.html             <-- Historico: timeline com duracao e datas amigaveis
      admin_devices.html         <-- Admin: criar devices
    static/
      style.css                  <-- CSS complementar ao Bootstrap 5
    agi/
      check_call.py              <-- AGI: autoriza chamadas (horario + permissao)
      log_call.py                <-- AGI: loga duracao apos desligar (hangup handler)
    deploy/
      setup-portal.sh            <-- Script de deploy automatico no VPS
      telefone-portal.service    <-- Systemd unit file (inclui SMTP + SITE_URL)
      nginx-telefone.conf        <-- Config nginx (reverse proxy + HTTPS)
      extensions.conf.new        <-- Dialplan atual (AGI + hangup handler)
```

### IMPORTANTE: Configs locais vs servidor

Os arquivos em `servidor/` sao copias LOCAIS e estao DESATUALIZADOS.
A versao autoritativa esta no VPS em `/etc/asterisk/`.

Para ver a config atual do servidor:
```bash
ssh -i ssh-key-2026-03-02.key ubuntu@163.176.157.229 "sudo cat /etc/asterisk/ARQUIVO"
```

O dialplan atual do servidor e baseado em `web/deploy/extensions.conf.new`.

## Script configurar-telefone.sh

Script que automatiza a configuracao completa de um novo telefone:
1. Gera senha SIP forte
2. Configura o HT802/HT801 via HTTP API (porta FXS 1)
3. Adiciona ramal no servidor Asterisk (pjsip_wizard.conf)
4. Cria device no portal web (com codigo de registro)
5. Reinicia o HT802

### Deteccao de duplicatas

O script verifica se o ramal ja existe:
- **No Asterisk**: pergunta se deseja sobrescrever (remove entrada antiga + adiciona nova)
- **No portal**: mostra info do device existente e pergunta:
  - Se ativado: pergunta se deseja desvincular usuario e resetar
  - Se nao ativado: pergunta se deseja gerar novo codigo de registro

### Como usar
```bash
bash configurar-telefone.sh
# Pede: IP do HT802, senha admin, numero do ramal, nome da crianca
```

### API do HT802V2/HT801 (firmware Vue.js)

O HT802V2/HT801 usa uma SPA Vue.js. Os endpoints da API:

- **Login**: `POST /cgi-bin/dologin`
  - Body: `username=admin&P2=<base64(senha)>`  (campo e P2, NAO password)
  - Header: `X-Requested-With: XMLHttpRequest`
  - Retorna: `{"response":"success","body":{"session_token":"..."}}`

- **Configurar**: `POST /cgi-bin/api.values.post`
  - Body: P-values + `apply=1` + `session_token=<token>`
  - O session_token vai NO BODY, nao como cookie

- **Reboot**: `POST /cgi-bin/rs`
  - Body: `session_token=<token>`

P-values usados (FXS PORT 1):
| P-value | Campo                  | Valor tipico        |
|---------|------------------------|---------------------|
| P271    | Account Active         | 1 (Yes)             |
| P47     | Primary SIP Server     | 163.176.157.229     |
| P35     | SIP User ID            | ramal (ex: 001)     |
| P36     | SIP Authenticate ID    | ramal (ex: 001)     |
| P34     | SIP Auth Password      | senha SIP gerada    |
| P3      | Display Name           | nome da crianca     |
| P52     | NAT Traversal          | 2 (Keep-Alive)      |
| P130    | SIP Transport          | 1 (TCP)             |
| P31     | SIP Registration       | 1 (Yes)             |
| P32     | Register Expiration    | 2 (120 seg)         |
| P81     | Unregister on Reboot   | 1 (Yes)             |

## Configuracao do Asterisk

### pjsip.conf (transportes)

OBRIGATORIO ter em cada transporte:
```ini
external_media_address = 163.176.157.229
external_signaling_address = 163.176.157.229
local_net = 10.0.0.0/16
```
Sem isso, o Asterisk anuncia o IP privado (10.0.0.x) no SDP e o audio nao funciona.

### pjsip_wizard.conf (ramais)

Usa formato **wizard** (NAO o formato antigo com sections separadas de endpoint/auth/aor).
O wizard cria automaticamente endpoint, auth (nome: XXX-iauth) e AOR com nomes corretos.

### extensions.conf (dialplan)

Baseado em `web/deploy/extensions.conf.new`:
- Contexto principal: `telefones-criancas`
- Ramal 100: hora certa (bypass, sem AGI)
- `_XXX`: qualquer ramal de 3 digitos passa pelo AGI `check_call.py`
- Antes do Dial: salva `CALL_DEST` e `CALL_START` (EPOCH)
- Apos desligar: hangup handler (`exten => h`) calcula duracao e chama `log_call.py`
- `_X.`: qualquer outro numero bloqueado
- Adicionar novo telefone NAO requer mudar o extensions.conf

### Firewall (iptables + Oracle Cloud)

Portas abertas no iptables E nas Security Lists da Oracle:
- **TCP 5060**: SIP sinalizacao
- **UDP 5060**: SIP sinalizacao (legado)
- **UDP 10000-20000**: RTP audio
- **TCP 80, 443**: Portal web (HTTP + HTTPS)

## Portal Web para Pais

### URL: https://telefone-fixo.duckdns.org

### Fluxo de ativacao

1. Pai acessa `/ativar`
2. Digita codigo de registro (8 chars, ex: G2GQ05LF)
3. Informa email, senha e nome da crianca
4. Recebe codigo de verificacao de 6 digitos por email
5. Confirma email em `/verificar-email`
6. Conta criada, device vinculado

### Funcionalidades

- Login/cadastro de pais (com verificacao de email por codigo de 6 digitos)
- Vincular aparelho por codigo de registro (8 chars alfanumerico)
- Configurar horarios permitidos por dia da semana (selects hora:minuto 24h)
- Autorizar/bloquear contatos (permissao bidirecional: ambos os lados precisam autorizar)
- Historico de ligacoes (com duracao e datas amigaveis: "5 mar 16:20")
- Dashboard redireciona direto ao device se usuario so tem 1 aparelho

### UX do portal

- Bootstrap 5 + Bootstrap Icons (CDN)
- Navbar escura com nome da crianca + ramal
- Tabs sticky: Contatos | Horarios permitidos | Historico
- Cards com bordas coloridas por status
- Contatos: 4 status (Pode ligar/verde, Aguardando outro/azul, Aguardando voce/amarelo, Bloqueado/cinza)
- Horarios: toggle por dia + selects hora:minuto (00/15/30/45/59)
- Historico: timeline com seta caller->destino, duracao, data amigavel

### Banco de dados (SQLite WAL)

Path no servidor: `/opt/telefone-portal/data/telefone.db`

- `users`: pais (email, senha bcrypt-like, is_admin, name)
- `devices`: aparelhos (extension, registration_code, child_name, user_id)
- `schedules`: horarios por dia (device_id, day_of_week 0-6, start_time, end_time)
- `permissions`: autorizacoes unidirecionais (device_id, allowed_extension)
- `call_logs`: historico (caller_ext, callee_ext, timestamp, status, duration_seconds, block_reason)

**Default: sem horario configurado = telefone funciona o dia todo.**
Horarios sao restricoes — so quando configurados, limitam o uso.

### AGI check_call.py

Path: `/var/lib/asterisk/agi-bin/check_call.py`
Symlink: `/usr/share/asterisk/agi-bin/check_call.py` -> acima (Asterisk procura aqui)

Logica:
1. Bypass para ramal 100 (hora certa)
2. Verifica se CALLER existe como device ativado (user_id IS NOT NULL)
3. Verifica se DESTINO existe como device ativado
4. Verifica horario do caller (sem schedule = liberado)
5. Verifica horario do destino (sem schedule = liberado)
6. Verifica permissao bidirecional (ambos os lados precisam ter autorizado)
7. Loga bloqueios no call_logs
8. Retorna CALL_RESULT=ALLOW ou BLOCK_*

### AGI log_call.py

Path: `/var/lib/asterisk/agi-bin/log_call.py`
Symlink: `/usr/share/asterisk/agi-bin/log_call.py`

Chamado pelo hangup handler (exten => h) apos qualquer chamada.
Le CALL_DEST, DIALSTATUS, CALL_DURATION e loga no call_logs com duracao.
Timestamps em horario de Sao Paulo (pytz).

### SMTP (email de verificacao)

Gmail app password configurada no systemd service (`telefone-portal.service`).
Variaveis: MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM.

### Deploy no VPS

```bash
# 1. Copiar arquivos
scp -i ssh-key-2026-03-02.key -r web/* ubuntu@163.176.157.229:/tmp/portal/

# 2. Rodar setup
ssh -i ssh-key-2026-03-02.key ubuntu@163.176.157.229 "bash /tmp/portal/deploy/setup-portal.sh"

# 3. Trocar extensions.conf (CUIDADO: testa antes!)
ssh -i ssh-key-2026-03-02.key ubuntu@163.176.157.229 \
  "sudo cp /tmp/portal/deploy/extensions.conf.new /etc/asterisk/extensions.conf && \
   sudo systemctl restart asterisk"

# 4. Criar symlinks dos AGIs
ssh -i ssh-key-2026-03-02.key ubuntu@163.176.157.229 \
  "sudo ln -sf /var/lib/asterisk/agi-bin/check_call.py /usr/share/asterisk/agi-bin/check_call.py && \
   sudo ln -sf /var/lib/asterisk/agi-bin/log_call.py /usr/share/asterisk/agi-bin/log_call.py"
```

## Licoes aprendidas / Armadilhas

1. **SIP ALG**: Roteadores domesticos tem SIP ALG que corrompe pacotes SIP UDP.
   Solucao: usar **TCP** como transporte SIP (P130=1 no HT802, transport-tcp no Asterisk).

2. **NAT do Oracle Cloud**: O VPS tem IP privado (10.0.0.x) e o Oracle faz NAT.
   Sem `external_media_address` no pjsip.conf, nao tem audio.

3. **Apos restart do Asterisk**: Conexoes TCP morrem. Os HT802 precisam ser
   reiniciados (desligar/ligar da tomada) para re-registrar. Ou esperar o timeout
   do registration (ate 120 seg).

4. **pjsip reload vs restart**: Adicionar NOVA secao no pjsip_wizard.conf requer
   `systemctl restart asterisk` (reload nao carrega secoes novas).

5. **HT802V2 login lockout**: Apos ~5 tentativas erradas, o HT802 bloqueia login.
   Reiniciar o HT802 (tomada) reseta o contador.

6. **Dois HT802 na mesma rede**: Precisam de portas SIP/RTP diferentes
   (ex: 5060/10000 e 5062/10002). Se em redes separadas, podem usar as mesmas.

7. **Descobrir IP do HT802**: Conectar telefone na porta FXS, tirar do gancho,
   discar `***02` — uma voz fala o IP.

8. **Enviar digitos no HT802**: Sempre terminar com `#` (ex: `067#`).
   O dialplan padrao do HT802 espera `#` como terminador.

9. **Porta FXS correta**: O telefone DEVE estar na porta PHONE 1 (porta de cima).
   Se estiver na PHONE 2, recebe chamadas mas NAO consegue discar.
   Isso e a causa mais comum de "nao consegue ligar" quando receber funciona.

10. **AGI path**: Asterisk procura AGIs em `/usr/share/asterisk/agi-bin/`, nao
    `/var/lib/asterisk/agi-bin/`. Criar symlinks.

11. **Permissao SQLite**: Usuario `asterisk` precisa estar no grupo `www-data`
    para escrever no banco. Arquivos .db com chmod 664.

12. **ANSWEREDTIME nao existe no Asterisk 18**: Usar `${EPOCH}` antes e depois
    do Dial() para calcular duracao. Hangup handler (`exten => h`) garante que
    o log acontece mesmo quando um lado desliga.

13. **HT801 compativel**: Mesma API e P-values que HT802, funciona sem alteracao
    no script.

14. **HT802 reset**: Botao RESET por 15-20s. Senha admin padrao muda apos reset
    (ver etiqueta no aparelho).

## Instrucoes para entregar aparelho aos pais

1. Configurar aparelho com `configurar-telefone.sh`
2. Anotar o codigo de registro que o script mostra no final
3. Informar aos pais:
   - Conectar telefone na **porta PHONE 1** (porta de cima do HT802)
   - Acessar https://telefone-fixo.duckdns.org/ativar
   - Usar o codigo de registro para ativar
   - Para ligar: discar ramal + **#** (ex: 067#)

## Preferencias do usuario

- Fazer o maximo automaticamente, so pedir intervencao quando acao fisica e necessaria
- Falar em portugues
- Nao usar emojis
- Manter as coisas simples e diretas
