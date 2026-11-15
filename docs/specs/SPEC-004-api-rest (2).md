# SPEC-004 — API REST

- **Status:** Vigente
- **Implementação:** `backend/app/main.py` (rotas), `backend/app/services.py` (regras). Documentação interativa em `/docs` com a API no ar.
- Os contratos de [`/pay`](SPEC-001-pagamento-idempotente.md) e do [`/webhooks/stripe`](SPEC-002-webhook-stripe.md) estão nas Specs próprias.

## 1. Convenções

- JSON em UTF-8. Valores monetários em **centavos inteiros**. Datas em ISO-8601 UTC.
- CORS liberado para as origens de `CORS_ORIGINS` (padrão `http://localhost:5173`); o header `Idempotent-Replayed` é exposto ao navegador.
- **Erros de negócio:** `{"detail": "mensagem em português"}`.
- **Erros de validação de formato** (Pydantic): `422` com `{"detail": [ … ]}` (lista). O cliente deve tratar `detail` como texto **ou** lista.

## 2. Rotas

| Método e rota | Função | Sucesso | Erros |
|---|---|---|---|
| `GET /health` | Verifica se a API está de pé | `200 {"ok": true}` | — |
| `GET /config` | Entrega a chave **pública** do Stripe | `200 {"publishable_key": "pk_test_…"}` | — |
| `GET /products` | Catálogo, ordenado por nome | `200 [Product]` | — |
| `POST /orders` | Cria o pedido (`pendente`) | `201 Order` | `422` produto inexistente, quantidade fora de 1–99 ou carrinho vazio |
| `GET /orders` | Os 20 pedidos mais recentes | `200 [Order]` | — |
| `GET /orders/{id}` | Detalhe do pedido | `200 Order` | `404` |
| `POST /orders/{id}/pay` | Inicia o pagamento ([SPEC-001](SPEC-001-pagamento-idempotente.md)) | `200 PayResponse` | `400`, `404`, `409`, `422`, `502` |
| `POST /orders/{id}/ship` | Marca como enviado (ação interna) | `200 Order` | `404`, `409` se o pedido não está `pago` |
| `POST /webhooks/stripe` | Recebe eventos ([SPEC-002](SPEC-002-webhook-stripe.md)) | `200 {outcome…}` | `400`, `500` |

> `POST /orders/{id}/ship` e `GET /orders` **não têm autenticação** (limitação conhecida, ver [AGENTS.md](../../AGENTS.md)).

## 3. Objetos

**`OrderIn`** (corpo de `POST /orders`)

```json
{ "items": [ { "product_id": "camiseta", "quantity": 2 } ] }
```

`items` com ao menos 1 elemento; `quantity` de 1 a 99. Produtos repetidos são somados. **Não há campo de preço.**

**`Product`**

```json
{ "id": "camiseta", "name": "Camiseta de algodão", "price_cents": 7990 }
```

**`Order`**

```json
{
  "id": "ord_3f9c1a2b4d5e6f70",
  "status": "pago",
  "total_cents": 15980,
  "currency": "brl",
  "payment_intent_id": "pi_…",
  "created_at": "2026-11-13T12:00:00.123456+00:00",
  "updated_at": "2026-11-13T12:00:07.654321+00:00",
  "items": [ { "product_id": "camiseta", "name": "Camiseta de algodão", "unit_price_cents": 7990, "quantity": 2 } ],
  "history": [
    { "from_status": null, "to_status": "pendente", "cause": "pedido_criado", "event_id": null, "occurred_at": "…" },
    { "from_status": "pendente", "to_status": "pago", "cause": "pagamento_confirmado", "event_id": "evt_…", "occurred_at": "…" }
  ]
}
```

`status` ∈ {`pendente`, `recusado`, `pago`, `enviado`, `estornado`}. O objeto **nunca** inclui `client_secret`.

**`PayResponse`**: `{"order_id", "payment_intent_id", "client_secret"}`.

## 4. Mapa de erros de domínio → HTTP

| Exceção | Status |
|---|---|
| `NotFound` | 404 |
| `InvalidOrder` | 422 |
| `IdempotencyConflict` | 422 |
| `NotPayable`, `InvalidTransition`, `RequestInProgress` | 409 |
| `MalformedEvent` | 400 |
| `GatewayUnavailable` | 502 |

Um único *exception handler* converte qualquer `DomainError` em `{"detail": message}` com o `status_code` da exceção.
