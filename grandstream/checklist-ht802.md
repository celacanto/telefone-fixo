# Checklist de Configuracao — Grandstream HT802/HT801

> **Nota:** O script `configurar-telefone.sh` faz toda essa configuracao automaticamente.
> Este checklist e apenas para referencia ou configuracao manual.

## Como acessar a interface web do HT802

1. Conecte o HT802 na rede (cabo ethernet no roteador)
2. Conecte um telefone na porta FXS 1 (porta de cima)
3. Tire o telefone do gancho e disque `***02`
4. Uma voz vai falar o IP do HT802 (ex: "192.168.1.105")
5. Abra o navegador e acesse: `http://IP_DO_HT802`
6. Login: **admin** / senha: (ver etiqueta na parte de baixo do HT802)

---

## Configuracao do ramal

### Aba: BASIC SETTINGS

| Campo                | Valor                          |
|----------------------|--------------------------------|
| Time Zone            | GMT-03:00 (Sao Paulo)          |

### Aba: FXS PORT 1

#### Account Settings
| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| Account Active              | Yes                            |
| Primary SIP Server          | `IP_DO_SEU_VPS`                |
| Failover SIP Server         | _(vazio)_                      |
| SIP Transport               | **TCP**                        |
| NAT Traversal               | Keep-Alive                     |

#### Account Registration
| Campo                       | Valor                                  |
|-----------------------------|----------------------------------------|
| SIP User ID                 | `RAMAL` (ex: 001)                      |
| Authenticate ID             | `RAMAL` (ex: 001)                      |
| Authenticate Password       | `SENHA_SIP` (gerada pelo script)       |
| Name                        | `NOME_DA_CRIANCA`                      |

#### Codec Settings
| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| Preferred Vocoder (escolha 1) | PCMU (G.711 u-law)          |
| Preferred Vocoder (escolha 2) | PCMA (G.711 a-law)          |

#### Misc
| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| SIP Registration            | Yes                            |
| Unregister on Reboot        | Yes                            |
| Register Expiration         | 120                            |
| Local SIP Port              | 5060                           |
| Local RTP Port              | 10000                          |

### Aba: FXS PORT 2

| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| Account Active              | **No** (desativar)             |

---

## Dois HT802 na mesma rede

Se os dois aparelhos estiverem na mesma rede (ex: fase de teste), as portas
SIP e RTP precisam ser diferentes:

- Aparelho 1: SIP Port 5060, RTP Port 10000
- Aparelho 2: SIP Port 5062, RTP Port 10002

Se estiverem em redes diferentes (casas diferentes), pode usar 5060/10000 nos dois.

---

## Apos configurar

1. Clique **Apply** e depois **Reboot** no HT802
2. Espere ~1 minuto
3. Tire o telefone do gancho — deve ter tom de discagem
4. Se nao tiver tom, verifique no Asterisk:
   ```
   asterisk -rx 'pjsip show endpoints'
   ```
   O ramal deve aparecer como "Available"

---

## Trocar senha do admin do HT802

Apos tudo funcionando, va em **ADVANCED SETTINGS > Admin Password** e troque
a senha padrao.
