# ADR-0011 — Processamento síncrono do webhook

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

O endpoint precisa responder `200` ao Stripe e aplicar a mudança de estado. O processamento são poucas instruções SQL.

## Decisão

A rota valida a assinatura e processa o evento na própria requisição, em *thread pool* (`run_in_threadpool`) porque o driver é bloqueante, respondendo `200` com o resultado.

## Consequências

- + Simples, e a resposta já informa o `outcome`, o que facilita demonstração e testes.
- + Sem infraestrutura extra.
- − Um pico de eventos disputa as mesmas conexões da API.
- − Regras pesadas no webhook atrasariam a resposta ao Stripe.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Fila (Celery, RQ, SQS) com *outbox* | `200` imediato e reprocessamento controlado, com mais peças a operar. Recomendada para volume alto. |
| `BackgroundTasks` do FastAPI | Perde a tarefa se o processo cair depois do `200`. |

## Referências

- `backend/app/main.py` → `stripe_webhook`, `deliver`

## Relacionados

[ADR-0003](0003-deduplicacao-de-webhook-por-insert.md)
