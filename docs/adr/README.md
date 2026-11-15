# Decisões de arquitetura (ADRs)

Cada ADR (*Architecture Decision Record*) registra **uma** decisão: o contexto, o que foi decidido, as consequências e as alternativas descartadas. Eles explicam o **porquê**; o **como** exato está nas [Specs](../specs/README.md).

| ADR | Decisão | Status |
|---|---|---|
| [0001](0001-webhook-como-fonte-da-verdade.md) | O webhook assinado é a fonte da verdade do estado do pagamento | Aceito |
| [0002](0002-prevencao-de-cobranca-duplicada.md) | Prevenção de cobrança duplicada em camadas (Idempotency-Key, um pagamento por pedido, travas no banco) | Aceito |
| [0003](0003-deduplicacao-de-webhook-por-insert.md) | Deduplicação de webhooks com INSERT primeiro, em uma transação única | Aceito |
| [0004](0004-assinatura-hmac-do-webhook.md) | Verificação manual da assinatura HMAC-SHA256 sobre o corpo bruto | Aceito |
| [0005](0005-maquina-de-estados-monotonica.md) | Máquina de estados em que o estado só avança | Aceito |
| [0006](0006-mysql-innodb-com-pymysql.md) | MySQL 8 (InnoDB) com PyMySQL e SQL explícito | Aceito |
| [0007](0007-paymentintent-com-payment-element.md) | PaymentIntent por pedido com o Payment Element | Aceito |
| [0008](0008-stripe-somente-em-modo-de-teste.md) | Somente Stripe em modo de teste, sem gateway simulado | Aceito |
| [0009](0009-dinheiro-em-centavos-e-preco-no-servidor.md) | Dinheiro em centavos inteiros e preço decidido pelo servidor | Aceito |
| [0010](0010-chamada-ao-stripe-fora-da-transacao.md) | Chamada ao Stripe fora da transação do banco | Aceito |
| [0011](0011-processamento-sincrono-do-webhook.md) | Processamento síncrono do webhook | Aceito |
| [0012](0012-polling-no-frontend.md) | Atualização da tela do pedido por polling | Aceito |
| [0013](0013-estrategia-de-testes.md) | Estratégia de testes em três níveis, com banco separado | Aceito |
| [0014](0014-entrega-de-webhooks-em-desenvolvimento.md) | Entrega de webhooks em desenvolvimento: Stripe CLI e script de demonstração | Aceito |

## Como criar ou alterar um ADR

1. **Decisão nova** que afete a arquitetura, uma regra de [AGENTS.md](../../AGENTS.md) ou um contrato das Specs: crie `docs/adr/NNNN-titulo-curto.md` com o próximo número.
2. **Decisão revista**: **não reescreva** o ADR antigo. Crie um novo, mude o status do antigo para `Substituído por ADR-NNNN` e atualize o índice acima.
3. Atualize as Specs e o [AGENTS.md](../../AGENTS.md) se o comportamento ou as regras mudarem, e os testes que comprovam a regra.

Status possíveis: `Proposto`, `Aceito`, `Substituído por ADR-NNNN`, `Rejeitado`.

## Modelo

```markdown
# ADR-NNNN — Título da decisão

- **Status:** Proposto | Aceito | Substituído por ADR-NNNN
- **Data:** AAAA-MM-DD

## Contexto
O problema e as forças em jogo.

## Decisão
O que foi decidido e como funciona.

## Consequências
- + ganho
- − custo

## Alternativas consideradas
| Alternativa | Por que não foi a escolhida |
|---|---|

## Referências
- código, testes, Specs

## Relacionados
```
