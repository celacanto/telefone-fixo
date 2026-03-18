# Como Adicionar um Novo Telefone

> **Nota:** O script `configurar-telefone.sh` faz tudo automaticamente.
> Este documento e apenas referencia.

## O que voce precisa

- 1x Grandstream HT801 ou HT802
- 1x Telefone com fio (qualquer um com plug RJ11)
- Acesso a internet na casa da crianca

## Passo a passo

### 1. Defina o numero do novo ramal

Escolha um numero de 3 digitos que ainda nao existe. Exemplos: 001, 002, 003...

### 2. Execute o script

```bash
export TELEFONE_VPS_IP=IP_DO_SEU_VPS
export TELEFONE_SSH_KEY=caminho/para/chave.key
bash configurar-telefone.sh
```

O script vai pedir o IP do adaptador, senha admin, ramal e nome. Ele configura tudo: adaptador, Asterisk e portal.

### 3. Teste

1. Tire o telefone do gancho — deve ter tom de discagem
2. Disque o ramal de outro telefone + # — deve tocar
3. Disque `100#` — deve falar a hora

### 4. Nao esqueca

- Troque a senha admin do adaptador
- Desative SIP ALG no roteador da casa (se houver problemas de audio)
