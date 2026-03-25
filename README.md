# Telefone Fixo para Crianças

Um telefone fixo para crianças ligarem umas para as outras.

A criança usa um telefone com fio comum, conectado a um pequeno aparelho adaptador (Grandstream HT801 ou HT802) que se liga à internet da casa. As ligações são feitas pela internet, sem custo de operadora.

## Como funciona

```
[Telefone] --> [Adaptador HT802] --internet--> [Servidor Asterisk] --internet--> [Adaptador HT802] --> [Telefone]
                                                       |
                                                [Portal Web]
                                                (controle dos pais)
```

- **Adaptadores**: Grandstream HT801 ou HT802 (convertem telefone analógico em VoIP)
- **Servidor**: Asterisk PBX na nuvem (Oracle Cloud Free Tier — gratuito)
- **Portal web**: Flask + SQLite no mesmo servidor, com HTTPS
- **Transporte SIP**: TCP (evita problemas com SIP ALG dos roteadores domésticos)

## Funcionalidades

- Crianças ligam umas para as outras discando ramal + #
- Chamada em grupo (até 5 participantes)
- Ligação para celular da família (até 2 celulares por criança)
- Portal web para as famílias controlarem:
  - Horários permitidos (quando o telefone pode ser usado)
  - Contatos autorizados (quem pode ligar para quem — bidirecional)
  - Histórico de ligações
- Mensagens de voz em português para cada situação (ocupado, fora do horário, etc.)
- Segurança: crianças só ligam para quem foi autorizado pelos dois lados

## Quanto custa

O projeto é inteiramente gratuito para rodar. O software é todo open-source (Asterisk, Flask, Linux) e o servidor roda na camada gratuita da Oracle Cloud.

O único investimento é o hardware:
- Adaptador Grandstream HT801 (~R$200) ou HT802 (~R$250) — um por casa
- Telefone com fio — qualquer um serve

## Guia de instalação

### 1. Servidor (VPS)

Crie uma VM gratuita na Oracle Cloud (VM.Standard.E2.1.Micro, Ubuntu):

```bash
# Instalar Asterisk
bash servidor/setup-vps.sh

# Configurar firewall
bash servidor/firewall.sh
```

Edite `servidor/pjsip.conf` substituindo `SEU_IP_PUBLICO` pelo IP do seu VPS e copie para `/etc/asterisk/`.

### 2. Portal web

```bash
# Copiar arquivos para o servidor
scp -i SUA_CHAVE_SSH -r web/* usuario@IP_DO_VPS:/tmp/portal/

# No servidor, rodar o setup (vai pedir email SMTP, IP, domínio)
ssh usuario@IP_DO_VPS "bash /tmp/portal/deploy/setup-portal.sh"

# Criar conta admin
ssh usuario@IP_DO_VPS "sudo /opt/telefone-portal/venv/bin/python /opt/telefone-portal/migrate.py"
```

Para HTTPS, configure DuckDNS + Let's Encrypt:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx
```

### 3. Dialplan

```bash
# Copiar o dialplan
sudo cp /tmp/portal/deploy/extensions.conf.new /etc/asterisk/extensions.conf

# Copiar AGIs
sudo cp /tmp/portal/agi/*.py /var/lib/asterisk/agi-bin/
sudo chmod +x /var/lib/asterisk/agi-bin/*.py
sudo ln -sf /var/lib/asterisk/agi-bin/check_call.py /usr/share/asterisk/agi-bin/
sudo ln -sf /var/lib/asterisk/agi-bin/check_group.py /usr/share/asterisk/agi-bin/
sudo ln -sf /var/lib/asterisk/agi-bin/conf_leave.py /usr/share/asterisk/agi-bin/
sudo ln -sf /var/lib/asterisk/agi-bin/log_call.py /usr/share/asterisk/agi-bin/

# Copiar configuração do ConfBridge
sudo cp /tmp/portal/deploy/confbridge.conf /etc/asterisk/confbridge.conf

# Reiniciar
sudo systemctl restart asterisk
```

### 4. Mensagens de voz

```bash
# Instalar dependências e gerar áudios em português
sudo apt install espeak-ng sox
sudo bash /tmp/portal/deploy/setup-group-audio.sh
```

Para mensagens de melhor qualidade, use Piper TTS (veja `web/deploy/setup-group-audio.sh`).

### 5. Adicionar um telefone

```bash
# Configurar variáveis de ambiente
export TELEFONE_VPS_IP=IP_DO_SEU_VPS
export TELEFONE_SSH_KEY=caminho/para/sua/chave.key

# Rodar o script
bash configurar-telefone.sh
```

O script vai pedir o IP do adaptador, senha admin, ramal e nome da criança. Ele configura tudo automaticamente: adaptador, Asterisk e portal.

### 6. Entregar para a família

1. Conectar telefone na **porta PHONE 1** (porta de cima do HT802)
2. Acessar o portal e usar o código de registro que o script mostrou
3. Para ligar: discar ramal + **#** (ex: 067#)

## Estrutura do projeto

```
telefone_fixo/
  configurar-telefone.sh     # Script automático: configura adaptador + servidor + portal
  servidor/                  # Configs do Asterisk (exemplos)
  grandstream/               # Checklist de configuração manual do adaptador
  web/
    app.py                   # Flask app principal
    models.py                # Schema SQLite
    config.py                # Configurações (tudo via variáveis de ambiente)
    agi/                     # Scripts AGI (verificação de permissões e horários)
    deploy/                  # Scripts de deploy e configs do servidor
    templates/               # Templates HTML (Bootstrap 5)
```

## Lições aprendidas

1. **SIP ALG**: Roteadores domésticos corrompem pacotes SIP UDP. Solução: usar TCP.
2. **NAT do Oracle Cloud**: Sem `external_media_address` no pjsip.conf, não tem áudio.
3. **Após restart do Asterisk**: Conexões TCP morrem. Os adaptadores re-registram em até 120s.
4. **Novo ramal**: Requer `systemctl restart asterisk` (reload não carrega seções novas).
5. **Porta FXS correta**: Telefone deve estar na porta PHONE 1 (de cima). Na PHONE 2, recebe mas não disca.
6. **AGI path**: Asterisk procura AGIs em `/usr/share/asterisk/agi-bin/`, não `/var/lib/`. Criar symlinks.
7. **Permissão SQLite**: Usuário `asterisk` precisa estar no grupo `www-data` para escrever no banco.

## Licença

MIT
