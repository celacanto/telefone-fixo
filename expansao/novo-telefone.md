# Como Adicionar um Novo Telefone

## O que você precisa

- 1x Grandstream HT802 (ou similar ATA VoIP)
- 1x Telefone com fio (qualquer um com plug RJ11)
- Acesso à internet na casa da criança

## Passo a passo

### 1. Defina o número do novo ramal

Escolha um número de 3 dígitos que ainda não existe. Exemplos:
- 002, 003, 004...
- Ou algo divertido: 042, 099...

### 2. Peça para o Claude configurar o servidor

Diga algo como:
> "Adicione o ramal XXX para o(a) [NomeCrianca] no Asterisk"

O Claude vai:
- Gerar uma senha forte
- Adicionar o ramal no `pjsip.conf`
- Adicionar no plano de discagem (`extensions.conf`)
- Autorizar chamadas de/para o novo ramal
- Atualizar o `credenciais.md`
- Recarregar o Asterisk

### 3. Configure o HT802 novo

Use o checklist abaixo (mesma estrutura do `checklist-ht802.md`):

#### Aba: BASIC SETTINGS
| Campo     | Valor                 |
|-----------|-----------------------|
| Time Zone | GMT-03:00 (São Paulo) |

#### Aba: FXS PORT 1
| Campo                  | Valor                     |
|------------------------|---------------------------|
| Account Active         | Yes                       |
| Primary SIP Server     | `IP_DO_VPS`               |
| SIP Transport          | UDP                       |
| NAT Traversal          | Keep-Alive                |
| SIP User ID            | `XXX` (número do ramal)   |
| Authenticate ID        | `XXX`                     |
| Authenticate Password  | (senha gerada pelo Claude)|
| Name                   | `NomeCrianca`             |
| Preferred Vocoder 1    | PCMU                      |
| Preferred Vocoder 2    | PCMA                      |
| SIP Registration       | Yes                       |
| Register Expiration    | 120                       |
| Local SIP Port         | 5060                      |
| Local RTP Port         | 10000                     |

#### Aba: FXS PORT 2
| Campo          | Valor |
|----------------|-------|
| Account Active | No    |

### 4. Teste

1. Tire o telefone do gancho — deve ter tom de discagem
2. Disque `067` — deve tocar no telefone do Inácio
3. Do telefone do Inácio, disque `XXX` — deve tocar no novo telefone
4. Disque `200` — deve tocar som engraçado
5. Disque `100` — deve falar a hora

### 5. Não esqueça

- Troque a senha admin do HT802 novo
- Anote tudo no `credenciais.md`
- Desative SIP ALG no roteador da casa do amigo (se houver problemas de áudio)
