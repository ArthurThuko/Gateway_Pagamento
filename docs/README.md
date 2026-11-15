# Documentação do projeto

Loja virtual com checkout via **Stripe (modo de teste)**, **MySQL** e **webhooks**. Backend em FastAPI, frontend em React.

Ponto de partida para quem vai alterar o código: [AGENTS.md](../AGENTS.md) (regras do projeto). Como executar: [README.md](../README.md).

## Mapa

| Documento | Responde a |
|---|---|
| [01 — Arquitetura e fluxo](01-arquitetura-e-fluxo.md) | Como o navegador (React), a API (FastAPI), o MySQL e o Stripe trabalham juntos? Para que serve a Stripe CLI? O que acontece quando algo falha? |
| [02 — Banco de dados](02-banco-de-dados.md) | Quais são as tabelas e colunas? Quem garante cada regra? Que travas cada operação usa? |
| [03 — Bibliotecas](03-bibliotecas.md) | Que bibliotecas e ferramentas o projeto usa, onde, e o que foi escolhido **não** usar? |
| [ADRs](adr/README.md) | **Por que** cada decisão foi tomada e quais alternativas foram descartadas? |
| [Specs](specs/README.md) | **Como exatamente** devem se comportar o pagamento, o webhook, a máquina de estados e a API? |

## As quatro perguntas do desafio

| Pergunta | Resposta em uma linha | Decisão | Contrato |
|---|---|---|---|
| Clique duplo em "Pagar": como evitar a cobrança dupla? | `Idempotency-Key` + um `PaymentIntent` por pedido + travas no banco | [ADR-0002](adr/0002-prevencao-de-cobranca-duplicada.md) | [SPEC-001](specs/SPEC-001-pagamento-idempotente.md) |
| O mesmo webhook chega 3 vezes: como processar uma só vez? | `INSERT` do `event.id` (chave primária) primeiro, numa transação única | [ADR-0003](adr/0003-deduplicacao-de-webhook-por-insert.md) | [SPEC-002](specs/SPEC-002-webhook-stripe.md) |
| Como saber que veio do gateway e não de um atacante? | HMAC-SHA256 sobre o corpo bruto, tempo constante, tolerância de 5 minutos | [ADR-0004](adr/0004-assinatura-hmac-do-webhook.md) | [SPEC-002](specs/SPEC-002-webhook-stripe.md) |
| "Pago" chega depois de "estornado": qual estado vale? | `estornado`: o estado só avança e o estorno é terminal | [ADR-0005](adr/0005-maquina-de-estados-monotonica.md) | [SPEC-003](specs/SPEC-003-maquina-de-estados.md) |

## Como a documentação se organiza

- **ADR** = *por quê*. Um arquivo por decisão, imutável depois de aceito (decisão revista vira ADR novo).
- **Spec** = *como exatamente*. Contratos, algoritmos, invariantes e casos de aceite ligados a testes.
- **01 a 03** = visão de conjunto (arquitetura, banco, bibliotecas), mantidos em sincronia com o código.
- **AGENTS.md** = as regras acionáveis, em formato de checklist, para quem altera o projeto.
