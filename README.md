# Loja com checkout, Stripe (modo de teste), MySQL e webhooks

Desafio 8 — *Checkout com gateway de pagamento e webhooks*.

Uma loja virtual em que o **Stripe (modo de teste)** confirma o pagamento **depois**, por uma notificação HTTP (webhook). O Stripe reenvia a notificação quando não recebe `200`, e a mesma notificação pode chegar **duplicada** ou **fora de ordem**. O sistema precisa continuar correto mesmo assim.

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| Banco | **MySQL 8** (InnoDB) via PyMySQL |
| Frontend | React 18 + Vite, Stripe Elements |
| Pagamento | **Stripe em modo de teste** (não há gateway simulado) |
| Segurança | Assinatura HMAC-SHA256 do webhook (formato `Stripe-Signature`) e header `Idempotency-Key` |
| Testes | pytest |

---

## 1. Estrutura

```
docker-compose.yml     # MySQL 8 para desenvolvimento
backend/
  app/
    state_machine.py   # máquina de estados do pedido (pura, sem I/O)
    signature.py       # HMAC-SHA256 + proteção contra replay
    services.py        # pedido, pagamento idempotente, processamento do webhook
    gateway.py         # StripeGateway (só chaves de teste)
    db.py              # esquema MySQL, conexão e transações
    main.py, config.py
  scripts/demo_webhooks.py   # demonstração com eventos reais do Stripe
  tests/                     # pytest
frontend/                    # React: loja, carrinho, pedido
```

Fluxo:

```
Navegador ──POST /orders──────────────▶ API   cria pedido (preço calculado no servidor) → PENDENTE
Navegador ──POST /orders/{id}/pay─────▶ API ──▶ Stripe   cria 1 PaymentIntent (Idempotency-Key)
Navegador ──confirmPayment (Stripe.js)────────▶ Stripe   o cartão vai direto ao Stripe
Stripe    ──POST /webhooks/stripe─────▶ API   verifica HMAC → deduplica → máquina de estados
Navegador ──GET /orders/{id} (polling)▶ API   vê o estado mudar quando o webhook chega
```

---

## 2. Como executar

### Pré-requisitos

- **Python 3.11+** e **Node.js 20+** (com npm)
- **Docker Desktop** (para o MySQL) — ou um MySQL 8 instalado por conta própria (veja abaixo)
- Conta no **Stripe** com o **modo de teste** ligado e a **[Stripe CLI](https://docs.stripe.com/stripe-cli)**
- Mac: `brew install python node` · Windows: instaladores de python.org (marque *Add python.exe to PATH*) e nodejs.org

### 1) Banco de dados MySQL

```bash
docker compose up -d        # igual no Mac e no Windows; cria o banco "loja" (usuário root, senha loja_dev)
```

> Porta 3306 ocupada (por exemplo, por um MySQL local)? Pare o outro serviço ou mude a porta em `docker-compose.yml` e em `MYSQL_PORT` no `.env`.
>
> **Sem Docker:** Mac `brew install mysql && brew services start mysql`; Windows: MySQL Installer (dev.mysql.com). Depois ajuste `MYSQL_USER` e `MYSQL_PASSWORD` no `.env`. O usuário precisa poder criar bancos (a aplicação cria `loja` e o pytest cria `loja_test`).

### 2) Chaves do Stripe (somente modo de teste)

1. No [Dashboard](https://dashboard.stripe.com/test/apikeys), com o modo de teste ligado, copie `sk_test_…` e `pk_test_…`.
2. Instale a Stripe CLI — Mac: `brew install stripe/stripe-cli/stripe`; Windows: `scoop bucket add stripe https://github.com/stripe/scoop-stripe-cli.git` e `scoop install stripe` (ou baixe o executável nas *releases* da CLI).
3. `stripe login` e, em um terminal separado, deixe rodando:
   ```bash
   stripe listen --api-key sk_test_SUA_CHAVE --events payment_intent.succeeded,payment_intent.payment_failed,charge.refunded --forward-to http://127.0.0.1:8000/webhooks/stripe
   ```
   - `--events` é obrigatório nas versões atuais da CLI; esses são os três eventos que a loja trata.
   - `--api-key` garante que a CLI escute a **mesma conta** das chaves do `.env` (se ela estiver logada em outra conta, nenhum evento chega).
   - Use `127.0.0.1` em vez de `localhost`: no Windows, `localhost` pode resolver para IPv6 e a API escuta em IPv4.
   - A CLI imprime um segredo `whsec_…`. Ele é o `STRIPE_WEBHOOK_SECRET`. Se você alterar o `.env`, **reinicie a API** (o `--reload` não observa o `.env`).

A aplicação **recusa iniciar** se as chaves não forem de teste (`sk_test_`, `pk_test_`, `whsec_`) e **recusa eventos com `livemode: true`**.

### 3) Backend

**Mac (Terminal)**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # preencha as 3 chaves do Stripe
uvicorn app.main:create_app --factory --reload --port 8000
```

**Windows (PowerShell)**

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env     # preencha as 3 chaves do Stripe
uvicorn app.main:create_app --factory --reload --port 8000
```

> Se o PowerShell bloquear o `Activate.ps1`, rode uma vez: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. No `cmd.exe` use `.venv\Scripts\activate.bat`.

As tabelas são criadas automaticamente na subida. API em http://localhost:8000 (documentação em `/docs`).

### 4) Frontend (outro terminal — igual no Mac e no Windows)

```bash
cd frontend
npm install
npm run dev
```

Abra http://localhost:5173, monte o carrinho e pague com o cartão `4242 4242 4242 4242` (aprovado) ou `4000 0000 0000 0002` (recusado), qualquer validade futura e CVC. Com o `stripe listen` ligado, o Stripe entrega o webhook e a tela do pedido muda de **Pendente** para **Pago** sozinha.

Para ver o **estorno**, abra o pagamento no Dashboard (modo de teste) e clique em *Reembolsar*: chega `charge.refunded`.

> `stripe trigger payment_intent.succeeded` cria um pagamento que **não** pertence a nenhum pedido da loja. O sistema responde `200` com `outcome: unknown_order` — comportamento esperado.

### Ordem para subir tudo

1. MySQL (`docker compose up -d`)
2. API (`uvicorn app.main:create_app --factory --port 8000`)
3. `stripe listen …` (comando acima) — **antes** de pagar: a CLI não reenvia eventos do passado
4. Frontend (`npm run dev`) e, só então, o pagamento

### Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `must specify events to forward using --events…` | Versão nova da CLI: use `--events` (ou `--all-snapshot`), como no comando acima. |
| Nada aparece no `stripe listen` | A CLI está logada em outra conta: use `--api-key sk_test_…`. Ou o pagamento ainda não foi confirmado. |
| `stripe listen` mostra `[400]` | `STRIPE_WEBHOOK_SECRET` diferente do `whsec_…` impresso pela CLI. Corrija o `.env` e reinicie a API. |
| `ERR_CONNECTION_REFUSED` no navegador / `connection refused` na CLI | A API caiu. Veja o traceback no terminal dela. Dentro do OneDrive o `--reload` pode reiniciar a API sem parar: tire o `--reload` ou mova o projeto para fora do OneDrive. |
| `This PaymentIntent is in a terminal state…` (400 do Stripe.js) | O pedido já foi pago, mas o webhook se perdeu (API ou CLI fora do ar na hora). O pedido fica *Pendente* e a tela oferece o formulário de novo. Abandone esse pedido, suba tudo na ordem acima e crie outro. |
| `stripe trigger …` responde `unknown_order` | Esperado: o evento não pertence a nenhum pedido da loja. Pague pelo site. |

### Testes automatizados

```bash
cd backend        # com o ambiente virtual ativado e o MySQL no ar
pytest -q
```

- Os testes usam um banco **separado** (`MYSQL_TEST_DATABASE`, padrão `loja_test`), criado automaticamente.
- Máquina de estados e assinatura não dependem de nada externo. Os testes de webhook usam só o MySQL.
- Os testes de pagamento (`@pytest.mark.stripe` e `test_api.py`) falam com o **Stripe real de teste**: precisam de rede e das chaves no `.env`. Sem as chaves, são **pulados**.

### Demonstração do desafio

Pré-requisitos: API e MySQL no ar, chaves no `.env` e o **`stripe listen` parado** (se estiver ligado, o Stripe entrega os eventos antes do script e o 1º envio já aparece como `duplicate`).

```bash
cd backend
python scripts/demo_webhooks.py        # Windows: py scripts\demo_webhooks.py
```

O script cria pedidos e pagamentos pela nossa API, confirma os pagamentos com cartões de teste no Stripe, busca os **eventos reais** gerados por ele e os entrega ao nosso webhook assinados com `STRIPE_WEBHOOK_SECRET`. Para o endpoint isso é indistinguível de uma entrega do Stripe. Três cenários:

1. **O mesmo webhook 5 vezes** → 1º envio `applied`, os outros 4 `duplicate`, todos com HTTP `200`; pedido `PAGO` com **uma** transição no histórico.
2. **Assinatura falsa** → HTTP `400` e o pedido continua `PENDENTE`. Em seguida, o *mesmo corpo* com a assinatura correta é aplicado: a única diferença é a assinatura.
3. **"Pago" depois de "estornado"** → o `pago` atrasado é `ignored`; o pedido continua `ESTORNADO`.

---

## 3. Decisões da equipe

### 3.1 Clicou duas vezes em "Pagar": como evitar a cobrança dupla?

Defesa em camadas — cada camada cobre a falha da anterior:

1. **Navegador:** o botão fica desabilitado e uma trava (`useRef`) ignora o segundo clique no mesmo instante. É conforto de UX, **não** é segurança.
2. **`Idempotency-Key` obrigatória** em `POST /orders/{id}/pay`. O navegador gera **uma chave por tentativa de pagamento**. O servidor guarda a resposta; a mesma chave devolve a **mesma resposta** (header `Idempotent-Replayed: true`), sem chamar o Stripe de novo. A mesma chave em *outro* pedido é rejeitada (`422`).
3. **Requisições simultâneas:** `SELECT … FOR UPDATE` na linha do pedido serializa tudo que mexe naquele pedido. A primeira "reivindica" a chave (`processing`) e solta a trava; a segunda recebe `409` e tenta de novo com a mesma chave. Uma chave `processing` abandonada expira em 60 s.
4. **Um pedido = no máximo um `PaymentIntent`.** Mesmo com chaves diferentes, o segundo pedido de pagamento reaproveita o `PaymentIntent` existente (índice `UNIQUE` em `payment_intent_id`). A chave enviada ao Stripe é derivada do pedido (`pay-<id>`): se o servidor cair entre "criou no Stripe" e "gravou no banco", a nova tentativa recebe o **mesmo** `PaymentIntent`.
5. **O próprio Stripe:** um `PaymentIntent` só pode ser pago uma vez; confirmar duas vezes não cobra duas vezes.
6. **Se o Stripe falhar**, a chave é liberada para o cliente tentar de novo com segurança.

### 3.2 O mesmo webhook chega 3 vezes: como processar só uma vez?

- Cada evento tem um `id` único (`evt_…`), usado como **chave primária** de `webhook_events`.
- O `INSERT` do `event.id` é o **primeiro comando** da transação. Se outra transação já o inseriu, o InnoDB faz esta **esperar** e, depois, devolve o erro 1062 (*duplicate key*): reenvios simultâneos viram um só processamento e os demais respondem `duplicate`.
- O `INSERT`, a **mudança de estado** e o registro do resultado ficam na **mesma transação**. Se algo falhar no meio, o `ROLLBACK` desfaz tudo (o evento **não** fica marcado como processado) e o reenvio do Stripe funciona. Há teste para isso.
- `SELECT … FOR UPDATE` no pedido garante que dois eventos *diferentes* do mesmo pedido (por exemplo, `pago` e `estornado` chegando juntos) sejam aplicados um de cada vez.
- **Sempre respondemos `200`** para evento duplicado, de tipo que não nos interessa ou de pedido desconhecido. Responder erro faria o Stripe reenviar por dias sem necessidade. Só respondemos `4xx/5xx` quando a **assinatura é inválida** (`400`) ou quando **nós** falhamos (`500`, para forçar o reenvio).

### 3.3 Como saber que a notificação vem do Stripe e não de um atacante?

- O Stripe assina o **corpo bruto** com HMAC-SHA256 usando um segredo que só ele e nós conhecemos: `v1 = HMAC(segredo, "<timestamp>." + corpo)`, enviado em `Stripe-Signature: t=…,v1=…`.
- Verificamos **antes de interpretar o JSON**, sobre os **bytes exatos** recebidos (reserializar o JSON mudaria os bytes e invalidaria a assinatura).
- Comparação em **tempo constante** (`hmac.compare_digest`).
- O timestamp entra na conta e tem **tolerância de 5 minutos**: um webhook verdadeiro, mas capturado e reenviado depois, é rejeitado (anti-replay).
- Aceitamos várias assinaturas `v1` no mesmo cabeçalho, o que permite **rotacionar o segredo** sem derrubar o endpoint.
- A assinatura foi implementada à mão (em vez de `stripe.Webhook.construct_event`) para demonstrar o mecanismo; o formato é idêntico ao do Stripe.

### 3.4 "Pago" chega depois de "estornado": qual estado vale?

Resposta: **estornado**. O desenho é uma máquina de estados em que **o estado só avança**:

```
pendente ──▶ pago ──▶ enviado ──▶ estornado
    │          ▲                       ▲
    ▼          │ (nova tentativa)      │ (estorno vale a partir de qualquer estado)
 recusado ─────┘───────────────────────┘
```

- Um estorno **prova** que houve pagamento, então `estornado` vale de qualquer estado — inclusive se chegar **antes** do `pago` (pulamos direto, e o `pago` atrasado é ignorado).
- `estornado` é **terminal**. Um `recusado` atrasado também não derruba um pedido `pago`.
- Como nenhuma transição volta atrás, **qualquer ordem de chegada leva ao mesmo estado final** (há teste com todas as permutações). Por isso **não usamos o timestamp do evento** para decidir ordem: relógios e reenvios não são confiáveis; a causalidade do negócio é.
- Eventos ignorados são registrados em `webhook_events` (`outcome = ignored`), e cada mudança aplicada vai para `order_history` — trilha de auditoria.
- `recusado → pago` é permitido porque o cliente pode tentar outro cartão no mesmo pedido.

### 3.5 Outras decisões

| Decisão | Motivo |
|---|---|
| **MySQL 8 / InnoDB** | Transações, índices `UNIQUE`/chave primária que deduplicam e `SELECT … FOR UPDATE` para travar por pedido (em vez de uma trava global). |
| **PyMySQL** (+ `cryptography`) | Driver em Python puro, instala igual no Mac e no Windows; o `cryptography` é exigido pela autenticação padrão do MySQL 8 (`caching_sha2_password`). |
| **Chamada ao Stripe fora da transação** | Não seguramos a trava da linha esperando a rede. |
| **Só Stripe em modo de teste, sem gateway simulado** | A aplicação exige `sk_test_`/`pk_test_`/`whsec_` e recusa eventos `livemode: true`. |
| **Testes sem gateway falso** | Webhook, assinatura e estados são testados com payloads no formato do Stripe como *dados de entrada* (`tests/events.py`); tudo que cria pagamento usa o Stripe real de teste e é pulado sem chaves. |
| **Banco de testes separado** | `loja_test`, limpo a cada teste: a suíte nunca apaga dados da loja. |
| Valores em **centavos inteiros** | Evita erro de ponto flutuante com dinheiro. |
| **Preço calculado no servidor** | O navegador só manda `product_id` e quantidade. |
| **Cartão nunca passa pelo nosso servidor** | Stripe Elements envia os dados direto ao Stripe (escopo PCI mínimo). |
| **O estado do pedido só muda por webhook** | O retorno do navegador pode falhar ou ser forjado; o webhook assinado é a fonte da verdade. A tela faz *polling*. |
| **Estorno parcial ignorado** (`refunded` ≠ `true`) | Fora do escopo; seria um estado novo (`parcialmente_estornado`). |

### 3.6 Limitações conhecidas

- Sem autenticação de usuários e de operador (a rota de envio e a listagem de pedidos são abertas para simplificar a demonstração).
- **Webhook perdido = pedido preso em *Pendente*.** O Stripe reenvia por até 3 dias, mas se a API ficar fora do ar mais que isso, ou a CLI não estiver escutando em desenvolvimento, o pagamento aprovado nunca chega ao pedido. Em produção, resolve-se com uma **reconciliação**: consultar o `PaymentIntent` no Stripe e aplicar o resultado pela mesma máquina de estados.
- O processamento do webhook é síncrono. Em produção: gravar o evento e processar em fila (*outbox*), respondendo `200` rápido.
- Os eventos da demonstração são reais, mas entregues pelo script (assinados com o segredo configurado), não pelo servidor do Stripe.
- Mercado Pago: a arquitetura permite trocar o gateway; mudariam o adaptador de criação de pagamento, o mapeamento de eventos e o formato do manifesto da assinatura `x-signature`.

---

## 4. O que cada teste cobre

| Arquivo | Regra do desafio | Precisa de |
|---|---|---|
| `test_pagamento_idempotente.py` | Clique duplo: mesma chave, chaves diferentes, chave em outro pedido, falha do Stripe, **6 requisições simultâneas** → 1 cobrança | MySQL + Stripe de teste |
| `test_webhook.py` | Mesmo webhook 3× e **8 threads simultâneas** → aplicado 1 vez; pago depois de estornado; recusado atrasado; `livemode`; rollback em falha | MySQL |
| `test_signature.py` | Assinatura válida, segredo errado, corpo adulterado, replay, cabeçalho malformado, rotação de segredo | nada |
| `test_state_machine.py` | Transições, `estornado` terminal, o estado só avança, **todas as permutações** convergem | nada |
| `test_api.py` | Ponta a ponta via HTTP: 5 reenvios → 200 ×5, assinatura falsa → 400, `Idempotency-Key` obrigatória | MySQL + Stripe de teste |