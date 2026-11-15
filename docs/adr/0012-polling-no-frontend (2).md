# ADR-0012 — Atualização da tela do pedido por polling

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

O estado do pedido muda quando o webhook é aplicado, não quando o navegador termina de confirmar o pagamento.

## Decisão

A tela do pedido chama `GET /orders/{id}` a cada 2 segundos enquanto está aberta.

## Consequências

- + Simples e robusto; sem conexão persistente.
- + Suficiente para um estado que muda uma ou duas vezes por pedido.
- − Requisições periódicas mesmo sem mudança.
- − Latência de até 2 s para mostrar o novo estado.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| WebSocket | Atualização instantânea, com conexão persistente e mais código. |
| Server-Sent Events | Mais simples que WebSocket, mas ainda exige infraestrutura de conexões longas. |

## Referências

- `frontend/src/App.jsx` → `Pedido`

## Relacionados

[ADR-0001](0001-webhook-como-fonte-da-verdade.md)
