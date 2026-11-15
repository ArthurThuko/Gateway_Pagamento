# ADR-0007 — PaymentIntent por pedido com o Payment Element

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

É preciso escolher como o Stripe coleta o pagamento. Queremos uma ligação direta entre pedido e pagamento, e eventos que mapeiem nos estados do pedido.

## Decisão

O backend cria **um `PaymentIntent` por pedido** (valor em BRL, `metadata.order_id`); o frontend abre o **Payment Element** com o `client_secret` e confirma pelo Stripe.js. Os eventos `payment_intent.succeeded`, `payment_intent.payment_failed` e `charge.refunded` mapeiam nos estados do pedido.

## Consequências

- + O pagamento existe antes da confirmação: ligação pedido ↔ pagamento (`payment_intent_id`, `metadata.order_id`) e idempotência de criação demonstráveis.
- + Cartão nunca passa pelo nosso servidor.
- − O console do navegador exibe um aviso do Stripe.js recomendando migrar para Checkout Sessions em integrações novas (não afeta o funcionamento).
- − Mais código de interface do que numa página hospedada.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Checkout Sessions (hospedado ou incorporado) | Recomendado pelo Stripe para integrações novas e com menos código. Provável melhor escolha para produção; aqui a ligação direta com o `PaymentIntent` serve melhor ao objetivo didático. |
| Payment Links | Sem vínculo programático com o nosso pedido. |
| Card Element (legado) | Substituído pelo Payment Element. |

## Referências

- `backend/app/gateway.py`
- `frontend/src/App.jsx` → `Pagamento`, `FormularioStripe`

## Relacionados

[ADR-0001](0001-webhook-como-fonte-da-verdade.md), [ADR-0008](0008-stripe-somente-em-modo-de-teste.md)
