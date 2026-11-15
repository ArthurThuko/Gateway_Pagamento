# Especificações (Specs)

Contratos e comportamento esperado do sistema: o **como exato**. O **porquê** está nos [ADRs](../adr/README.md).

| Spec | Assunto | Decisões |
|---|---|---|
| [SPEC-001](SPEC-001-pagamento-idempotente.md) | `POST /orders/{id}/pay`: pagamento idempotente | ADR-0002, 0007, 0010 |
| [SPEC-002](SPEC-002-webhook-stripe.md) | `POST /webhooks/stripe`: autenticação, deduplicação e processamento | ADR-0001, 0003, 0004, 0008, 0011 |
| [SPEC-003](SPEC-003-maquina-de-estados.md) | Estados, eventos e transições do pedido | ADR-0005 |
| [SPEC-004](SPEC-004-api-rest.md) | Demais rotas, objetos e mapa de erros | ADR-0009 |

## Como usar

- Cada Spec termina com **casos de aceite**, ligados ao teste que os comprova. Mudou o comportamento? Atualize a Spec **e** o teste.
- Se a mudança contraria uma decisão registrada, escreva um ADR novo (veja [como criar um ADR](../adr/README.md)).
- Nas Specs, "invariante" é uma propriedade que **nunca** pode ser violada; regras de [AGENTS.md](../../AGENTS.md) apontam para elas.
