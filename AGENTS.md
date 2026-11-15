# AGENTS.md — Regras do projeto

Guia para **quem altera este repositório**, pessoas ou agentes de IA. Resume o projeto, os comandos, as **regras aplicadas** e as armadilhas. O porquê de cada regra está nos [ADRs](docs/adr/README.md); o contrato exato, nas [Specs](docs/specs/README.md).

## 1. O projeto em um parágrafo

Loja virtual (Desafio 8: *checkout com gateway de pagamento e webhooks*). O **Stripe**, em modo de teste, confirma o pagamento **depois**, por webhook; o webhook pode chegar duplicado ou fora de ordem. Backend **FastAPI** + **MySQL 8**; frontend **React** (Vite) com Stripe Elements. O sistema deve ser correto diante de: clique duplo em "Pagar", webhook repetido, webhook forjado e eventos fora de ordem.

## 2. Mapa do repositório

```
AGENTS.md  README.md  docs/            # esta documentação
backend/
  app/
    main.py            # rotas FastAPI (HTTP)
    services.py        # regras de negócio (sem HTTP)
    state_machine.py   # transições do pedido (pura)
    signature.py       # HMAC-SHA256 do webhook (pura)
    gateway.py         # único ponto que fala com o Stripe
    db.py              # esquema MySQL, conexão, transaction()
    config.py          # variáveis de ambiente e validação das chaves
  scripts/demo_webhooks.py
  tests/               # pytest
frontend/src/          # App.jsx, api.js, main.jsx
```

Arquitetura completa: [docs/01-arquitetura-e-fluxo.md](docs/01-arquitetura-e-fluxo.md). Banco: [docs/02-banco-de-dados.md](docs/02-banco-de-dados.md). Bibliotecas: [docs/03-bibliotecas.md](docs/03-bibliotecas.md).

## 3. Comandos

Pré-requisitos: Python 3.11+, Node 20+, **MySQL 8.0.16+** rodando, Stripe CLI, chaves de teste do Stripe.

**Backend** (a partir de `backend/`)

| | Mac / Linux | Windows (PowerShell) |
|---|---|---|
| Ambiente virtual | `python3 -m venv .venv && source .venv/bin/activate` | `py -m venv .venv` e `.venv\Scripts\Activate.ps1` (Git Bash: `source .venv/Scripts/activate`) |
| Dependências | `pip install -r requirements.txt` | idem |
| Configuração | `cp .env.example .env` | `Copy-Item .env.example .env` |

```bash
uvicorn app.main:create_app --factory --port 8000     # API (acrescente --reload ao desenvolver)
stripe listen --api-key sk_test_… --events payment_intent.succeeded,payment_intent.payment_failed,charge.refunded --forward-to http://127.0.0.1:8000/webhooks/stripe
pytest -q                                             # testes
python scripts/demo_webhooks.py                       # demonstração (com o `stripe listen` PARADO)
```

**Frontend** (a partir de `frontend/`): `npm install` e `npm run dev` → http://localhost:5173.

Ordem para subir tudo: MySQL → API → `stripe listen` → frontend.

## 4. Regras do projeto

Estas regras são **invariantes**: mudá-las exige um ADR novo (veja a seção 9).

### Pagamento e Stripe

| # | Regra | Por quê / onde |
|---|---|---|
| R1 | **Só um webhook autenticado muda o estado do pagamento** (`pago`, `recusado`, `estornado`). O retorno do navegador **nunca** altera o pedido. A única outra mudança é o envio interno (`pago → enviado`) | [ADR-0001](docs/adr/0001-webhook-como-fonte-da-verdade.md) |
| R2 | `POST /orders/{id}/pay` **exige** `Idempotency-Key`. Um pedido tem **no máximo um** `PaymentIntent` (`UNIQUE`), criado no Stripe com a chave `pay-<order_id>` | [ADR-0002](docs/adr/0002-prevencao-de-cobranca-duplicada.md), [SPEC-001](docs/specs/SPEC-001-pagamento-idempotente.md) |
| R3 | **Nunca** chamar o Stripe (ou qualquer rede) dentro de uma transação | [ADR-0010](docs/adr/0010-chamada-ao-stripe-fora-da-transacao.md) |
| R4 | **Somente modo de teste**: `sk_test_`, `pk_test_`, `whsec_`; rejeitar `livemode: true`. **Não** criar gateway simulado nem *mock* do Stripe para a aplicação | [ADR-0008](docs/adr/0008-stripe-somente-em-modo-de-teste.md) |
| R5 | Dinheiro em **centavos inteiros**. O preço vem **sempre do banco**; o cliente só envia `product_id` e quantidade | [ADR-0009](docs/adr/0009-dinheiro-em-centavos-e-preco-no-servidor.md) |

### Webhook

| # | Regra | Por quê / onde |
|---|---|---|
| R6 | Verificar a assinatura **antes** de interpretar o JSON, sobre os **bytes brutos** (nunca reserializar). Comparação em tempo constante e tolerância de timestamp | [ADR-0004](docs/adr/0004-assinatura-hmac-do-webhook.md), `signature.py` |
| R7 | Deduplicar com **`INSERT` do `event_id` primeiro**, na **mesma transação** da mudança de estado. **Nunca** "`SELECT` e depois `INSERT`" | [ADR-0003](docs/adr/0003-deduplicacao-de-webhook-por-insert.md), `process_webhook` |
| R8 | Respostas do webhook: `200` para duplicado, ignorado, `unrelated` e `unknown_order`; `400` só para assinatura inválida, JSON inválido, evento malformado ou `livemode`; falhas nossas ficam `500` (para o Stripe reenviar). **Não** capturar exceções inesperadas para devolver `200` | [SPEC-002](docs/specs/SPEC-002-webhook-stripe.md) |
| R9 | Registrar **todo** evento aceito em `webhook_events`, inclusive os ignorados | [docs/02-banco-de-dados.md](docs/02-banco-de-dados.md) |

### Estado

| # | Regra | Por quê / onde |
|---|---|---|
| R10 | **Toda** mudança de `orders.status` passa por `state_machine.decide` e `_apply_transition` (que também grava `order_history`). **Nunca** `UPDATE orders SET status` solto | [SPEC-003](docs/specs/SPEC-003-maquina-de-estados.md) |
| R11 | **O estado só avança.** Não adicionar transições que retrocedam. `estornado` é terminal. **Não** ordenar eventos por timestamp | [ADR-0005](docs/adr/0005-maquina-de-estados-monotonica.md) |

### Banco

| # | Regra | Por quê / onde |
|---|---|---|
| R12 | Toda operação sensível trava a linha do pedido (`SELECT … FOR UPDATE`) **antes** de decidir. Ordem de travas: webhook = `webhook_events` → `orders`; pagamento = `orders` → `idempotency_keys`. Nunca na ordem inversa | [docs/02-banco-de-dados.md](docs/02-banco-de-dados.md) §5 |
| R13 | **SQL sempre parametrizado** (`%s`). Nada de *f-string* com valores. Exceções já existentes: nome do banco (validado por regex) e nomes de tabelas fixos | [ADR-0006](docs/adr/0006-mysql-innodb-com-pymysql.md) |
| R14 | Unicidade vem do **banco** (PK e `UNIQUE`), não de variável em memória | [ADR-0002](docs/adr/0002-prevencao-de-cobranca-duplicada.md) |

### Código

| # | Regra | Por quê / onde |
|---|---|---|
| R15 | **Camadas:** `main → services → (state_machine, gateway, db)`. `services.py` **não** importa FastAPI; `state_machine.py` e `signature.py` ficam **puros** (sem I/O) | [docs/01-arquitetura-e-fluxo.md](docs/01-arquitetura-e-fluxo.md) §5 |
| R16 | Erros de negócio são subclasses de `DomainError` com `status_code`; o `main.py` os converte em JSON. **Não** levantar `HTTPException` em `services.py` | `services.py` |
| R17 | O `client_secret` **só** sai em `POST /orders/{id}/pay`. Nenhuma rota de leitura o devolve | [SPEC-004](docs/specs/SPEC-004-api-rest.md) |

## 5. Convenções

- **Idioma:** documentação, comentários, *docstrings*, mensagens ao usuário e variáveis locais de domínio em **português (pt-BR)**; nomes de módulos, funções, classes, tabelas e colunas em **inglês**.
- **Python 3.11+:** *type hints* com `X | None`; `dataclass` para valores; `Enum` com `str`.
- **Configuração:** variáveis de ambiente lidas em `config.py` (carregador próprio de `.env`; sem `python-dotenv`). Nunca ler `os.environ` fora dele.
- **Frontend:** JavaScript (sem TypeScript), `fetch` nativo, estado local com hooks. A `Idempotency-Key` é gerada **uma por tentativa** (`useRef(crypto.randomUUID())`).
- **Mensagens de commit:** imperativo e curto (por exemplo, "Adiciona trava por pedido no pagamento").

## 6. Testes

| Nível | Arquivos | Precisa de |
|---|---|---|
| Puros | `test_state_machine.py`, `test_signature.py` | nada |
| MySQL | `test_webhook.py` | MySQL |
| Stripe real | `test_pagamento_idempotente.py` (marcador `stripe`), `test_api.py` | MySQL + chaves de teste (sem elas, são **pulados**) |

Regras:

1. Toda regra central tem teste. Concorrência se testa com *threads* e **conexões separadas**, não em sequência.
2. Os testes usam o banco `loja_test` (esvaziado a cada teste); a suíte recusa rodar se for igual a `MYSQL_DATABASE`.
3. Payloads de webhook dos testes vêm de `tests/events.py` (dado de entrada). **Não** simular o Stripe para pagamentos (R4).
4. Mudou comportamento? Atualize a **Spec** e o teste que a comprova.

## 7. Segurança e segredos

- `.env` fica **fora do Git** (já no `.gitignore`). Só `.env.example`, com valores fictícios, é versionado.
- Nunca registrar em *log*: `sk_test_`, `whsec_`, `client_secret` ou dados de cartão. O cartão **nunca** passa pela API (Stripe Elements).
- A chave `pk_test_` é pública; as demais (`sk_test_`, `whsec_`) ficam **só** no backend.
- Ao rodar fora de desenvolvimento, usar HTTPS e cadastrar o endpoint no Dashboard do Stripe.

## 8. Armadilhas conhecidas

| Sintoma | Causa e solução |
|---|---|
| `must specify events to forward using --events…` | A CLI atual exige `--events` (ou `--all-snapshot`) |
| Nada chega no `stripe listen` | CLI logada em outra conta: usar `--api-key sk_test_…`. A CLI **não** reenvia eventos do passado |
| Webhook responde `400` | `STRIPE_WEBHOOK_SECRET` diferente do `whsec_` impresso pela CLI. Reiniciar a API depois de mudar o `.env` (o `--reload` não observa o `.env`) |
| `ERR_CONNECTION_REFUSED` | A API caiu. Dentro do OneDrive, o `--reload` pode reiniciar sem parar: rodar sem `--reload` ou mover o projeto |
| `localhost` não conecta no Windows | IPv6: usar `127.0.0.1` |
| `PaymentIntent is in a terminal state` | O pedido já foi pago, mas o webhook se perdeu. Abandonar o pedido e criar outro |
| `AttributeError: 'get' is a dict method` | O SDK novo do Stripe não devolve `dict`: converter com `.to_dict()` (ver `demo_webhooks.py`) |
| Primeiro envio do script já é `duplicate` | O `stripe listen` estava ligado durante a demonstração |
| `CHECK` de preço não é aplicado | MySQL anterior a 8.0.16 |

## 9. Como mudar o projeto

1. **Leia** a Spec e o ADR da área que vai mexer.
2. Se a mudança **contraria** uma regra deste arquivo ou um ADR: escreva um **ADR novo** (o antigo passa a `Substituído por ADR-NNNN`) **antes** do código. Modelo em [docs/adr/README.md](docs/adr/README.md).
3. Altere o código **respeitando as camadas** (R15).
4. Atualize a **Spec**, os docs 01 a 03 e este arquivo se o comportamento, o banco ou as bibliotecas mudaram.
5. Rode `pytest -q` e, se tocou em pagamento ou webhook, a demonstração.

**Pronto quando:** testes passam; a Spec e o teste correspondente estão atualizados; nenhuma regra R1–R17 foi violada sem ADR; nenhum segredo foi versionado.

## 10. Limitações conhecidas

- **Webhook perdido = pedido preso em `pendente`.** Evolução: reconciliação consultando o `PaymentIntent` e aplicando o resultado pela mesma máquina de estados.
- Processamento **síncrono** do webhook (evolução: fila com *outbox*).
- **Sem autenticação** de usuários e de operador (`/orders` e `/orders/{id}/ship` abertos).
- Estorno **parcial** ignorado.
- Sem *pool* de conexões nem logs estruturados.
- Apenas Stripe (a interface `PaymentGateway` permite adaptar outro, com novo mapeamento de eventos e assinatura).

## 11. Documentação

[docs/README.md](docs/README.md) · [01 Arquitetura e fluxo](docs/01-arquitetura-e-fluxo.md) · [02 Banco de dados](docs/02-banco-de-dados.md) · [03 Bibliotecas](docs/03-bibliotecas.md) · [ADRs](docs/adr/README.md) · [Specs](docs/specs/README.md)
