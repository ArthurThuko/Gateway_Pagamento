# SPEC-001 — Pagamento idempotente (`POST /orders/{order_id}/pay`)

- **Status:** Vigente
- **Decisões relacionadas:** [ADR-0002](../adr/0002-prevencao-de-cobranca-duplicada.md), [ADR-0010](../adr/0010-chamada-ao-stripe-fora-da-transacao.md), [ADR-0007](../adr/0007-paymentintent-com-payment-element.md)
- **Implementação:** `backend/app/services.py` → `pay_order`; `backend/app/main.py` → `pay`

## 1. Objetivo

Iniciar o pagamento de um pedido criando (ou reaproveitando) **um** `PaymentIntent` no Stripe, de modo que repetir a chamada — por duplo clique, duas abas ou *retry* de rede — **nunca** gere duas cobranças.

## 2. Requisição

| Item | Regra |
|---|---|
| Método e rota | `POST /orders/{order_id}/pay` |
| Header `Idempotency-Key` | **Obrigatório**, 1 a 200 caracteres. O navegador gera uma por tentativa de pagamento |
| Corpo | Nenhum |

## 3. Respostas

**Sucesso — `200`**

```json
{ "order_id": "ord_…", "payment_intent_id": "pi_…", "client_secret": "pi_…_secret_…" }
```

Header `Idempotent-Replayed: true` quando a resposta foi **reaproveitada** da `idempotency_keys` (mesma chave repetida); `false` caso contrário.

**Erros** (corpo `{"detail": "mensagem"}`)

| Status | Quando |
|---|---|
| `400` | Header `Idempotency-Key` ausente ou com mais de 200 caracteres |
| `404` | Pedido inexistente |
| `409` | Já existe pagamento em andamento (`RequestInProgress`), ou o pedido não está `pendente` nem `recusado` (`NotPayable`) |
| `422` | A mesma `Idempotency-Key` foi usada em **outro** pedido (`IdempotencyConflict`), inclusive por corrida no `INSERT` da chave |
| `502` | O Stripe falhou ao criar o pagamento (`GatewayUnavailable`); a chave é liberada |

## 4. Pré-condição

O pedido está em `pendente` ou `recusado` (este último permite nova tentativa com outro cartão).

## 5. Algoritmo

**Transação 1** (`BEGIN … COMMIT`)

1. `SELECT … FROM orders WHERE id = ? FOR UPDATE` — serializa tudo que ocorre neste pedido. Inexistente → `404`.
2. Procura a chave em `idempotency_keys`:
   - existe para **outro** pedido → `422`;
   - existe e `state = done` → devolve `response_json` com `replayed = true` (fim);
   - existe e `state = processing` há **menos de 60 s** → `409`;
   - existe e `processing` há 60 s ou mais (abandonada) → apaga e segue.
3. Estado do pedido fora de `pendente`/`recusado` → `409`.
4. Se `orders.payment_intent_id` já existe → grava a chave como `done` com a resposta montada a partir do pedido e devolve (**sem** chamar o Stripe; `replayed = false`).
5. Se há outra chave `processing` recente para o pedido → `409`.
6. `INSERT` da chave com `state = processing`. Chave duplicada por corrida → `422`.

**Chamada ao Stripe — fora de qualquer transação**

7. `PaymentIntent.create(amount, currency, automatic_payment_methods, metadata.order_id)` com `idempotency_key = "pay-<order_id>"`. Falha → transação curta apaga a chave; responde `502`.

**Transação 2**

8. `UPDATE orders` com `payment_intent_id` e `client_secret`; `UPDATE idempotency_keys` para `done` com `response_json`. Devolve `200`.

## 6. Invariantes

| # | Invariante | Garantida por |
|---|---|---|
| I1 | Um pedido tem **no máximo um** `PaymentIntent` | `UNIQUE (payment_intent_id)` e passo 4 |
| I2 | A mesma `Idempotency-Key` devolve a **mesma** resposta | PK de `idempotency_keys` e passo 2 |
| I3 | Uma chave pertence a **um** pedido | Passo 2 |
| I4 | O Stripe recebe no máximo uma criação por pedido, mesmo com queda entre os passos 7 e 8 | Chave `pay-<order_id>` |
| I5 | Nenhuma trava do banco é mantida durante a chamada ao Stripe | Passos 6 e 7 em transações distintas |
| I6 | O `client_secret` só é devolvido por esta rota | `get_order` não o inclui |

## 7. Casos de aceite

| # | Dado / Quando / Então | Teste |
|---|---|---|
| A1 | Pedido pendente; duas chamadas com a mesma chave → mesma resposta; `replayed` `false` e depois `true`; **uma** chamada ao Stripe | `test_clique_duplo_com_mesma_chave_cria_um_unico_pagamento` |
| A2 | Duas chaves diferentes no mesmo pedido → mesmo `payment_intent_id`; uma chamada ao Stripe | `test_chaves_diferentes_no_mesmo_pedido_reaproveitam_o_pagamento` |
| A3 | Mesma chave em outro pedido → `IdempotencyConflict` | `test_mesma_chave_em_outro_pedido_e_rejeitada` |
| A4 | Pedido já pago → `NotPayable` | `test_pedido_pago_nao_aceita_novo_pagamento` |
| A5 | Stripe falha → `GatewayUnavailable`, nenhuma chave sobra; repetir com a mesma chave funciona | `test_falha_do_stripe_libera_a_chave_para_nova_tentativa` |
| A6 | 6 requisições simultâneas (chaves repetidas e distintas) → **uma** chamada ao Stripe e um único `payment_intent_id` | `test_cliques_simultaneos_nunca_geram_duas_cobrancas` |
| A7 | O pagamento criado no Stripe tem o valor e a `metadata.order_id` do pedido | `test_pagamento_no_stripe_tem_valor_e_metadata_corretos` |
| A8 | Sem o header → `400` | `test_pagar_exige_idempotency_key` |
| A9 | Chave repetida pela API → `Idempotent-Replayed: true` | `test_clique_duplo_devolve_a_mesma_resposta` |
