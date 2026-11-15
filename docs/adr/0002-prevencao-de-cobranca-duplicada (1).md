# ADR-0002 — Prevenção de cobrança duplicada em camadas (Idempotency-Key, um pagamento por pedido, travas no banco)

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

Dois cliques em "Pagar", duas abas ou um *retry* de rede não podem gerar duas cobranças. Nenhuma proteção isolada cobre todos os casos: a do navegador não vale contra duas abas; a do banco não vale contra uma queda no meio; a do Stripe não impede nossa base de ficar inconsistente.

## Decisão

Seis camadas, cada uma cobrindo a falha da anterior:

1. **Navegador:** botão desabilitado e trava `useRef`. Só conforto de UX.
2. **`Idempotency-Key` obrigatória** em `POST /orders/{id}/pay`, gerada pelo navegador (uma por tentativa). A resposta é guardada em `idempotency_keys`; a mesma chave devolve a mesma resposta (`Idempotent-Replayed: true`) sem chamar o Stripe. A mesma chave em outro pedido é rejeitada (`422`).
3. **Exclusão mútua por pedido:** `SELECT … FOR UPDATE` na linha de `orders`. A primeira requisição registra a chave como `processing` e solta a trava; concorrentes recebem `409`. Chave `processing` com mais de 60 s é considerada abandonada.
4. **Um pedido, no máximo um `PaymentIntent`:** índice `UNIQUE (payment_intent_id)`; chaves diferentes no mesmo pedido **reaproveitam** o pagamento existente.
5. **Chave de idempotência derivada do pedido no Stripe** (`pay-<order_id>`): se o servidor cair entre "criou no Stripe" e "gravou no banco", a nova tentativa recebe o mesmo `PaymentIntent`.
6. **O próprio Stripe:** um `PaymentIntent` só é pago uma vez.

Se o Stripe falhar, a chave é **liberada** para o cliente tentar de novo.

## Consequências

- + Uma falha em qualquer camada ainda termina em no máximo uma cobrança.
- + A garantia vem do banco, não de memória da aplicação: vale com vários processos e sobrevive a reinício.
- − Estado intermediário `processing` e uma resposta `409` que o cliente precisa saber repetir.
- − Mais tabelas e mais regras em `pay_order`.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Só desabilitar o botão | Não protege contra duas abas, *retry* ou chamada direta à API. Mantido como complemento. |
| Depender só da idempotência do Stripe | Nossa base poderia ficar inconsistente, e as chaves do Stripe expiram após algum tempo. |
| Idempotência em Redis (`SET NX`) | Peça extra de infraestrutura e sem atomicidade com o banco. |
| Trava distribuída (Redlock, `GET_LOCK`) | Complexidade e modos de falha próprios; aqui existe uma linha natural para travar. |
| Controle otimista (coluna `version`) | Exige *retry* e expõe o conflito ao usuário. |
| Apenas `UNIQUE` em `payment_intent_id` | Impede a gravação duplicada, não a chamada duplicada ao Stripe. Mantido como complemento. |

## Referências

- `backend/app/services.py` → `pay_order`
- `backend/app/db.py` → `idempotency_keys`, `orders.payment_intent_id`
- `tests/test_pagamento_idempotente.py`
- [SPEC-001](../specs/SPEC-001-pagamento-idempotente.md)

## Relacionados

[ADR-0006](0006-mysql-innodb-com-pymysql.md), [ADR-0010](0010-chamada-ao-stripe-fora-da-transacao.md)
