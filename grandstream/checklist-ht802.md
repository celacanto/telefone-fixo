# Checklist de Configuração — Grandstream HT802

## Como acessar a interface web do HT802

1. Conecte o HT802 na rede (cabo ethernet no roteador)
2. Conecte um telefone na porta FXS 1
3. Tire o telefone do gancho e disque `***02`
4. Uma voz vai falar o IP do HT802 (ex: "192.168.1.105")
5. Abra o navegador e acesse: `http://IP_DO_HT802`
6. Login: **admin** / senha: (ver etiqueta na parte de baixo do HT802)

---

## HT802 #1 — Casa do Inácio

### Aba: BASIC SETTINGS

| Campo                | Valor                          |
|----------------------|--------------------------------|
| Time Zone            | GMT-03:00 (São Paulo)          |
| Self-Defined Time Zone | _(deixar vazio)_             |

### Aba: FXS PORT 1 (ramal 067 — Inácio)

#### Account Settings
| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| Account Active              | Yes                            |
| Primary SIP Server          | `163.176.157.229`                    |
| Failover SIP Server         | _(vazio)_                      |
| SIP Transport               | **TCP**                        |
| NAT Traversal               | Keep-Alive                     |

#### Account Registration
| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| SIP User ID                 | `067`                          |
| Authenticate ID             | `067`                          |
| Authenticate Password       | `mQ2rinixVJe2nxAiof9P6A`      |
| Name                        | `Inacio`                       |
| Profile Name (na tela)      | `Inacio`                       |

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
| Account Active              | **No** (desativar por enquanto)|

---

## HT802 #2 — Casa do Amigo

### Aba: BASIC SETTINGS

| Campo                | Valor                          |
|----------------------|--------------------------------|
| Time Zone            | GMT-03:00 (São Paulo)          |

### Aba: FXS PORT 1 (ramal 001 — Amigo)

#### Account Settings
| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| Account Active              | Yes                            |
| Primary SIP Server          | `163.176.157.229`                    |
| Failover SIP Server         | _(vazio)_                      |
| SIP Transport               | **TCP**                        |
| NAT Traversal               | Keep-Alive                     |

#### Account Registration
| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| SIP User ID                 | `001`                          |
| Authenticate ID             | `001`                          |
| Authenticate Password       | `QLWjHyJPIolCWNdH1oNbeA`      |
| Name                        | `Amigo`                        |
| Profile Name (na tela)      | `Amigo`                        |

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
| Local SIP Port              | 5062                           |
| Local RTP Port              | 10002                          |

> **Nota:** se os dois HT802 estiverem na MESMA rede (fase de teste), as portas
> SIP e RTP precisam ser diferentes. HT802 #1 usa 5060/10000, HT802 #2 usa
> 5062/10002. Se estiverem em redes diferentes (casas diferentes), pode usar
> 5060/10000 nos dois.

### Aba: FXS PORT 2

| Campo                       | Valor                          |
|-----------------------------|--------------------------------|
| Account Active              | **No** (desativar por enquanto)|

---

## Após configurar

1. Clique **Apply** e depois **Reboot** no HT802
2. Espere ~1 minuto
3. Tire o telefone do gancho — deve ter tom de discagem
4. Se não tiver tom, verifique no Asterisk:
   ```
   asterisk -rx 'pjsip show endpoints'
   ```
   O ramal deve aparecer como "Available"

---

## Fase 1: Teste na mesma casa

Para testar com os dois na mesma casa:
- HT802 #1, porta 1: telefone do Inácio (ramal 067)
- HT802 #2, porta 1: simula o amigo (ramal 001)
- Os dois HT802 conectados no mesmo roteador
- **Lembre de usar portas diferentes** (5060 vs 5062, 10000 vs 10002)
- Do telefone 067, disque `001` — o outro telefone deve tocar
- Do telefone 001, disque `067` — o telefone do Inácio deve tocar
- Disque `100` de qualquer um — deve falar a hora
- **IMPORTANTE:** disque o número e aperte `#` para enviar (ex: `001#`)

## Trocar senha do admin do HT802

Após tudo funcionando, vá em **ADVANCED SETTINGS → Admin Password** e troque
a senha padrão. Anote a nova senha no `credenciais.md`.
