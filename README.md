# Telefone Fixo para Criancas

Um telefone fixo para criancas ligarem umas para as outras.

A crianca usa um telefone com fio comum, conectado a um pequeno aparelho adaptador (Grandstream HT801 ou HT802) que se liga a internet da casa. As ligacoes sao feitas pela internet, sem custo de operadora.

## Como funciona

```
[Telefone] --> [Adaptador HT802] --internet--> [Servidor Asterisk] --internet--> [Adaptador HT802] --> [Telefone]
                                                       |
                                                [Portal Web]
                                                (controle dos pais)
```

- **Adaptadores**: Grandstream HT801 ou HT802 (convertem telefone analogico em VoIP)
- **Servidor**: Asterisk PBX na nuvem (Oracle Cloud Free Tier — gratuito)
- **Portal web**: Flask + SQLite no mesmo servidor, com HTTPS
- **Transporte SIP**: TCP (evita problemas com SIP ALG dos roteadores domesticos)

## Funcionalidades

- Criancas ligam umas para as outras discando ramal + #
- Chamada em grupo (ate 5 participantes)
- Ligacao para celular da familia (ate 2 celulares por crianca)
- Portal web para as familias controlarem:
  - Horarios permitidos (quando o telefone pode ser usado)
  - Contatos autorizados (quem pode ligar para quem — bidirecional)
  - Historico de ligacoes
- Mensagens de voz em portugues para cada situacao (ocupado, fora do horario, etc.)
- Seguranca: criancas so ligam para quem foi autorizado pelos dois lados

## Quanto custa

O projeto e inteiramente gratuito para rodar. O software e todo open-source (Asterisk, Flask, Linux) e o servidor roda na camada gratuita da Oracle Cloud.

O unico investimento e o hardware:
- Adaptador Grandstream HT801 (~R$200) ou HT802 (~R$250) — um por casa
- Telefone com fio — qualquer um serve

## Guia de instalacao

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

# No servidor, rodar o setup (vai pedir email SMTP, IP, dominio)
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

# Copiar configuracao do ConfBridge
sudo cp /tmp/portal/deploy/confbridge.conf /etc/asterisk/confbridge.conf

# Reiniciar
sudo systemctl restart asterisk
```

### 4. Mensagens de voz

```bash
# Instalar dependencias e gerar audios em portugues
sudo apt install espeak-ng sox
sudo bash /tmp/portal/deploy/setup-group-audio.sh
```

Para mensagens de melhor qualidade, use Piper TTS (veja `web/deploy/setup-group-audio.sh`).

### 5. Adicionar um telefone

```bash
# Configurar variaveis de ambiente
export TELEFONE_VPS_IP=IP_DO_SEU_VPS
export TELEFONE_SSH_KEY=caminho/para/sua/chave.key

# Rodar o script
bash configurar-telefone.sh
```

O script vai pedir o IP do adaptador, senha admin, ramal e nome da crianca. Ele configura tudo automaticamente: adaptador, Asterisk e portal.

### 6. Entregar para a familia

1. Conectar telefone na **porta PHONE 1** (porta de cima do HT802)
2. Acessar o portal e usar o codigo de registro que o script mostrou
3. Para ligar: discar ramal + **#** (ex: 067#)

## Estrutura do projeto

```
telefone_fixo/
  configurar-telefone.sh     # Script automatico: configura adaptador + servidor + portal
  servidor/                  # Configs do Asterisk (exemplos)
  grandstream/               # Checklist de configuracao manual do adaptador
  web/
    app.py                   # Flask app principal
    models.py                # Schema SQLite
    config.py                # Configuracoes (tudo via variaveis de ambiente)
    agi/                     # Scripts AGI (verificacao de permissoes e horarios)
    deploy/                  # Scripts de deploy e configs do servidor
    templates/               # Templates HTML (Bootstrap 5)
```

## Licoes aprendidas

1. **SIP ALG**: Roteadores domesticos corrompem pacotes SIP UDP. Solucao: usar TCP.
2. **NAT do Oracle Cloud**: Sem `external_media_address` no pjsip.conf, nao tem audio.
3. **Apos restart do Asterisk**: Conexoes TCP morrem. Os adaptadores re-registram em ate 120s.
4. **Novo ramal**: Requer `systemctl restart asterisk` (reload nao carrega secoes novas).
5. **Porta FXS correta**: Telefone deve estar na porta PHONE 1 (de cima). Na PHONE 2, recebe mas nao disca.
6. **AGI path**: Asterisk procura AGIs em `/usr/share/asterisk/agi-bin/`, nao `/var/lib/`. Criar symlinks.
7. **Permissao SQLite**: Usuario `asterisk` precisa estar no grupo `www-data` para escrever no banco.

## Licenca

MIT
