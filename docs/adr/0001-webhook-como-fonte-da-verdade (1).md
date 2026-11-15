# ADR-0001 — O webhook assinado é a fonte da verdade do estado do pagamento

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

Depois de `confirmPayment`, o navegador sabe o resultado imediato, mas esse resultado não serve como registro: a aba pode fechar, a rede pode cair e a resposta pode ser forjada por quem controla o navegador. O Stripe, por outro lado, notifica o resultado por webhook, mesmo que o cliente suma.

## Decisão

O retorno do navegador **não altera o pedido**. O estado `pago`, `recusado` ou `estornado` só nasce de um webhook autenticado (ver [ADR-0004](0004-assinatura-hmac-do-webhook.md)). A tela do pedido consulta `GET /orders/{id}` periodicamente ([ADR-0012](0012-polling-no-frontend.md)). A única outra fonte de mudança é uma ação interna da loja: `POST /orders/{id}/ship` (`pago → enviado`).

## Consequências

- + O pagamento aprovado é registrado mesmo se o cliente fechar a aba.
- + Um único canal confiável e independente do navegador.
- − Latência de alguns segundos entre o pagamento e a mudança de estado na tela.
- − Obriga a tratar duplicidade e ordem ([ADR-0003](0003-deduplicacao-de-webhook-por-insert.md), [ADR-0005](0005-maquina-de-estados-monotonica.md)).
- − Um webhook perdido deixa o pedido em `pendente` (limitação conhecida; evolução: reconciliação consultando o `PaymentIntent`).

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Confiar no retorno do navegador (`return_url` / `confirmPayment`) | Falha se a aba fechar e pode ser forjado. Serviria no máximo como atualização otimista da tela. |
| Consultar o Stripe periodicamente a partir do servidor | Atraso, custo de chamadas e limites de taxa. É útil como **reconciliação complementar**, não como mecanismo principal. |
| `success_url` do Checkout hospedado | Mesmo problema de confiar no redirecionamento do cliente. |

## Referências

- `backend/app/services.py` → `process_webhook`
- `frontend/src/App.jsx` → `Pedido` (polling)
- [SPEC-002](../specs/SPEC-002-webhook-stripe.md)

## Relacionados

[ADR-0003](0003-deduplicacao-de-webhook-por-insert.md), [ADR-0004](0004-assinatura-hmac-do-webhook.md), [ADR-0005](0005-maquina-de-estados-monotonica.md), [ADR-0012](0012-polling-no-frontend.md)
