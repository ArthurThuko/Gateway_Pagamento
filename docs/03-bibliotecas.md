# 03 — Bibliotecas e ferramentas

Tudo o que o projeto usa e **onde** cada peça aparece. As versões mínimas vêm de `backend/requirements.txt` e `frontend/package.json`; o que foi escolhido **não** usar também está registrado, para evitar reintroduzir por engano.

## 1. Backend (Python 3.11+)

Instaladas por `pip install -r requirements.txt`.

| Biblioteca | Versão mín. | Para que serve | Onde |
|---|---|---|---|
| **fastapi** | 0.110 | Framework da API: rotas, validação, injeção de dependência, CORS, `TestClient` | `app/main.py`, `tests/test_api.py` |
| **uvicorn[standard]** | 0.29 | Servidor ASGI que executa a API. O extra `standard` traz o `watchfiles` (usado pelo `--reload`) | linha de comando |
| **stripe** | 9.0 | SDK oficial: cria o `PaymentIntent`; na demonstração confirma pagamentos, estorna e lista eventos | `app/gateway.py`, `scripts/demo_webhooks.py`, `tests/test_pagamento_idempotente.py` |
| **PyMySQL** | 1.1 | Driver do MySQL em Python puro | `app/db.py` |
| **cryptography** | 42.0 | Exigida pelo PyMySQL na autenticação padrão do MySQL 8 (`caching_sha2_password`). Não é importada pelo nosso código | indireta |
| **pytest** | 8.0 | Testes automatizados (fixtures, `parametrize`, `monkeypatch`, marcadores) | `tests/` |
| **httpx** | 0.27 | Cliente HTTP em que o `TestClient` do FastAPI se apoia | `tests/test_api.py` (indireta) |

### Dependências que vêm junto (não declaradas por nós)

| Biblioteca | Vem de | O que usamos |
|---|---|---|
| **starlette** | fastapi | `run_in_threadpool` (executa o código bloqueante do webhook fora do laço de eventos) em `app/main.py` |
| **pydantic** | fastapi | `BaseModel` e `Field` para validar o corpo de `POST /orders` (`ItemIn`, `OrderIn`) |
| **watchfiles** | uvicorn[standard] | Recarregamento automático (`--reload`) |

### Biblioteca padrão do Python

| Módulo | Uso |
|---|---|
| `hmac`, `hashlib` | Assinatura HMAC-SHA256 do webhook (`app/signature.py`); `hmac.compare_digest` para comparação em tempo constante |
| `json` | Corpo guardado em `idempotency_keys`; leitura do webhook; script de demonstração |
| `threading` | Testes de concorrência (`tests/`) e contador thread-safe do espião de chamadas |
| `uuid` | Ids de pedido (`ord_…`) |
| `time`, `datetime` | Timestamps de assinatura, `created_epoch`, `now_iso()` |
| `dataclasses`, `enum`, `typing` | `Settings`, `Decision`, `PayResult`, `WebhookResult`; `OrderStatus` e `OrderEvent`; `Protocol` do gateway |
| `contextlib` | `transaction()` como *context manager* (`app/db.py`) |
| `os`, `pathlib`, `re` | Carregamento do `.env` e validação do nome do banco |
| `urllib` | Chamadas HTTP do script de demonstração (sem dependência extra) |
| `itertools` | `permutations` nos testes da máquina de estados |

## 2. Frontend (Node.js 20+)

Instaladas por `npm install`.

| Biblioteca | Versão mín. | Para que serve | Onde |
|---|---|---|---|
| **react** | 18.3.1 | Interface: `useState`, `useEffect`, `useMemo`, `useRef` | `src/App.jsx` |
| **react-dom** | 18.3.1 | Renderização no navegador (`createRoot`) | `src/main.jsx` |
| **@stripe/stripe-js** | 5.0 | Carrega o Stripe.js (`loadStripe`) com a chave pública | `src/App.jsx` |
| **@stripe/react-stripe-js** | 3.0 | Componentes do Stripe para React: `Elements`, `PaymentElement`, `useStripe`, `useElements` | `src/App.jsx` |
| **vite** | 5.4 | Servidor de desenvolvimento e empacotamento (porta 5173) | `vite.config.js` |
| **@vitejs/plugin-react** | 4.3 | Suporte a JSX/React no Vite | `vite.config.js` |

APIs nativas do navegador: `fetch` (chamadas à API), `crypto.randomUUID()` (gera a `Idempotency-Key`), `setInterval` (polling) e `Intl` via `toLocaleString` (moeda em reais).

## 3. Ferramentas fora do código

| Ferramenta | Versão | Para que serve |
|---|---|---|
| **Python** | 3.11+ | Backend e testes |
| **Node.js / npm** | 20+ | Frontend |
| **MySQL** | 8.0.16+ | Banco (versões anteriores ignoram o `CHECK`) |
| **Stripe CLI** | atual | `stripe listen` (encaminha webhooks ao `localhost`), `stripe trigger`, `stripe login` |
| **Conta Stripe** | modo de teste | Chaves `sk_test_`, `pk_test_` e segredo `whsec_` |
| **Git** | — | Versionamento |

## 4. Mapa: onde cada biblioteca entra no fluxo

| Etapa do fluxo | Bibliotecas |
|---|---|
| Navegador monta o carrinho e cria o pedido | react, fetch |
| Navegador gera a `Idempotency-Key` | `crypto.randomUUID()` |
| API recebe e valida a requisição | fastapi, pydantic, uvicorn |
| API grava no MySQL | PyMySQL (+ cryptography) |
| API cria o pagamento | stripe |
| Navegador coleta o cartão | @stripe/stripe-js, @stripe/react-stripe-js |
| Stripe avisa a API | Stripe CLI (em desenvolvimento) |
| API valida o webhook | `hmac` e `hashlib` |
| Código bloqueante roda sem travar a API | starlette (`run_in_threadpool`) |
| Verificação automatizada | pytest, httpx, `threading` |

## 5. O que **não** usamos (e por quê)

Estas escolhas estão justificadas nos ADRs; listá-las aqui evita reintroduzi-las sem discussão.

| Não usado | Motivo | Registro |
|---|---|---|
| **SQLAlchemy / ORM** | O SQL explícito deixa visíveis o `INSERT` na chave primária e o `FOR UPDATE`, que sustentam a correção | [ADR-0006](adr/0006-mysql-innodb-com-pymysql.md) |
| **Alembic** (migrações) | O esquema é pequeno e criado por `init_db`; migrações entram quando o esquema evoluir em produção | [ADR-0006](adr/0006-mysql-innodb-com-pymysql.md) |
| **python-dotenv** | O carregador de `.env` é um trecho curto em `app/config.py` | [AGENTS.md](../AGENTS.md) |
| **`stripe.Webhook.construct_event`** | A verificação foi implementada à mão para explicitar cada passo; o formato é idêntico | [ADR-0004](adr/0004-assinatura-hmac-do-webhook.md) |
| **Redis / Celery / filas** | A trava vem do MySQL e o webhook é processado de forma síncrona | [ADR-0003](adr/0003-deduplicacao-de-webhook-por-insert.md), [ADR-0011](adr/0011-processamento-sincrono-do-webhook.md) |
| **Mocks do SDK / `stripe-mock` / gateway falso** | Decisão da equipe: Stripe real em modo de teste | [ADR-0008](adr/0008-stripe-somente-em-modo-de-teste.md) |
| **WebSocket / SSE** | O estado muda poucas vezes por pedido; polling basta | [ADR-0012](adr/0012-polling-no-frontend.md) |
| **TypeScript, React Router, Tailwind, axios** | Fora do escopo do desafio; `fetch` nativo atende | — |
