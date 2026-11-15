# ADR-0005 — Máquina de estados em que o estado só avança

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

Eventos podem chegar em qualquer ordem, e cada reenvio traz timestamps diferentes. É preciso decidir, por exemplo, qual estado vale quando `pago` chega depois de `estornado`.

## Decisão

O estado segue a ordem `pendente < recusado < pago < enviado < estornado` e **nenhuma transição retrocede**. `estornado` vale a partir de qualquer estado e é terminal (um estorno prova que houve pagamento; se chegar antes do `pago`, o pedido vai direto para `estornado` e o `pago` atrasado é ignorado). Um `recusado` atrasado não derruba um pedido `pago`. `recusado → pago` é permitido (novo cartão no mesmo pedido). Só estorno **total** é tratado. A decisão **não usa** timestamps de evento. Toda mudança passa por `state_machine.decide`.

## Consequências

- + O estado final depende só do conjunto de eventos, não da ordem de chegada (testado com todas as permutações).
- + Módulo puro, sem banco: fácil de testar e de explicar.
- + Eventos ignorados ficam registrados para auditoria.
- − Estorno parcial fica fora do escopo (exigiria novo estado).
- − Um evento verdadeiramente inconsistente (ex.: `pago` depois de `enviado`) é ignorado em vez de sinalizado.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Ordenar por `event.created` | Reenvios e relógios não garantem ordem; segundos iguais empatam. |
| Consultar o estado atual no Stripe a cada evento | Sempre correto, mas com latência e dependência da API a cada webhook. Útil em reconciliação. |
| *Event sourcing* completo | Complexidade desproporcional para cinco estados. |
| Aceitar qualquer transição ("o último vence") | Um `pago` atrasado ressuscitaria um pedido estornado. |
| Ignorar `estornado` que chega antes de `pago` | Perderia um estorno real e deixaria o pedido pago após devolver o dinheiro. |

## Referências

- `backend/app/state_machine.py`
- `tests/test_state_machine.py`
- [SPEC-003](../specs/SPEC-003-maquina-de-estados.md)

## Relacionados

[ADR-0001](0001-webhook-como-fonte-da-verdade.md), [ADR-0003](0003-deduplicacao-de-webhook-por-insert.md)
