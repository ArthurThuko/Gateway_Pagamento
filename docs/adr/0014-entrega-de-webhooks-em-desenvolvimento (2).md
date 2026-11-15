# ADR-0014 — Entrega de webhooks em desenvolvimento: Stripe CLI e script de demonstração

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

O Stripe não alcança `localhost`. Além disso, a demonstração precisa repetir, forjar e inverter a ordem de eventos sob demanda, o que o Stripe não permite.

## Decisão

Em desenvolvimento, `stripe listen --events … --forward-to http://127.0.0.1:8000/webhooks/stripe` encaminha os eventos reais. Na demonstração, `scripts/demo_webhooks.py` cria pagamentos reais, busca os **eventos reais** (`Event.list`) e os entrega ao webhook, assinados com `STRIPE_WEBHOOK_SECRET`, com a Stripe CLI **parada** (senão o Stripe entregaria os eventos antes).

## Consequências

- + Sem expor a máquina na internet.
- + Demonstração determinística: 5 reenvios, assinatura falsa, ordem invertida.
- − No script, a assinatura é gerada localmente, não pelo servidor do Stripe; para o endpoint é indistinguível, pois a verificação é a mesma conta HMAC.
- − Duas formas de entrega para manter coerentes.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Túnel público (ngrok, Cloudflare) e endpoint no Dashboard | Cenário idêntico ao de produção e permite "reenviar" pelo Dashboard, mas exige conta e URL pública. |
| Somente o script | Determinístico, porém não mostra a entrega real do Stripe. |

## Referências

- `backend/scripts/demo_webhooks.py`
- README, seção "Demonstração do desafio"

## Relacionados

[ADR-0004](0004-assinatura-hmac-do-webhook.md), [ADR-0008](0008-stripe-somente-em-modo-de-teste.md)
