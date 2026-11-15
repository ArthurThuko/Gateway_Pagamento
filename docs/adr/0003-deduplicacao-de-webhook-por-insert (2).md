# ADR-0003 — Deduplicação de webhooks com INSERT primeiro, em uma transação única

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

O Stripe reenvia o mesmo evento (mesmo `event.id`) quando não recebe `200` a tempo, e reenvios podem chegar **ao mesmo tempo**. "Verificar se já vi o evento e depois gravar" em dois passos tem uma janela de corrida.

## Decisão

`process_webhook` abre uma transação e executa, nesta ordem: (1) `INSERT` do `event_id` em `webhook_events` (chave primária) — se já existir, o InnoDB faz a transação esperar a outra terminar e devolve o erro 1062, e a resposta é `duplicate`; (2) `SELECT … FOR UPDATE` no pedido; (3) decisão da máquina de estados e, se aplicável, `UPDATE` do pedido e `INSERT` em `order_history`; (4) `UPDATE` do resultado em `webhook_events` e `COMMIT`.

Tudo é uma só transação: qualquer falha provoca `ROLLBACK`, inclusive do `INSERT` do evento, que **não** fica marcado como processado.

A resposta é sempre `200` para duplicado, ignorado, `unrelated` e `unknown_order`; `400` só para assinatura inválida ou evento malformado; falhas nossas viram `500`, para forçar o reenvio.

## Consequências

- + A chave primária é a fonte de exclusão mútua: o banco resolve a concorrência.
- + Reenvios simultâneos viram um só processamento.
- + Falha no meio do caminho não deixa o evento "perdido": o reenvio funciona.
- − Depende de comportamento específico do InnoDB (espera em chave duplicada e erro 1062).
- − Eventos que não tratamos também ocupam linhas em `webhook_events`.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| `SELECT` e depois `INSERT` | Janela de corrida entre os dois passos. |
| `INSERT IGNORE` e checar linhas afetadas | Equivalente; preferimos a exceção 1062 por tornar explícitas a espera do InnoDB e o *rollback* total. |
| Conjunto de ids em memória | Perde-se no reinício e não vale para mais de um processo. |
| Redis (`SET NX`) | Não é atômico com a mudança de estado no banco. |
| Deduplicar por *hash* do corpo | Reenvios podem diferir em bytes; `event.id` é o identificador oficial. |
| Fila com *outbox* | Mais robusta a picos, mas com mais infraestrutura ([ADR-0011](0011-processamento-sincrono-do-webhook.md)). |

## Referências

- `backend/app/services.py` → `process_webhook`
- `backend/app/db.py` → `webhook_events`, `is_duplicate`
- `tests/test_webhook.py`
- [SPEC-002](../specs/SPEC-002-webhook-stripe.md)

## Relacionados

[ADR-0001](0001-webhook-como-fonte-da-verdade.md), [ADR-0006](0006-mysql-innodb-com-pymysql.md), [ADR-0011](0011-processamento-sincrono-do-webhook.md)
