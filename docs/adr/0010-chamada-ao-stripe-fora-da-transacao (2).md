# ADR-0010 — Chamada ao Stripe fora da transação do banco

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

A chamada ao Stripe é uma operação de rede de duração imprevisível. Se ocorresse dentro de uma transação, a trava da linha do pedido ficaria retida durante a espera.

## Decisão

Em `pay_order`, a transação 1 reivindica a chave (`processing`) e faz `COMMIT`; só então ocorre a chamada ao Stripe; a transação 2 grava o resultado. Em caso de falha, uma transação curta apaga a chave.

## Consequências

- + Não seguramos travas nem conexões esperando a rede.
- − Surge o estado intermediário `processing`, tratado com `409` para concorrentes e com prazo de 60 s para chaves abandonadas.
- − A consistência entre "criou no Stripe" e "gravou no banco" depende da idempotência do Stripe (chave `pay-<order_id>`).

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Manter a transação aberta durante a chamada | Trava a linha por tempo imprevisível e pode esgotar conexões. |
| *Outbox* e *worker* | Isola totalmente a rede, mas com infraestrutura extra. |

## Referências

- `backend/app/services.py` → `pay_order`

## Relacionados

[ADR-0002](0002-prevencao-de-cobranca-duplicada.md)
