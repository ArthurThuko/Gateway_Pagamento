# ADR-0013 — Estratégia de testes em três níveis, com banco separado

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

As regras difíceis são as de **concorrência** (clique duplo, reenvios simultâneos) e de **ordem** (permutação de eventos). Testes sequenciais não as exercitam.

## Decisão

Três níveis: (1) **puros** — máquina de estados (todas as permutações) e assinatura, sem dependências; (2) **com MySQL** — webhook: duplicidade, 8 *threads* simultâneas, ordem trocada, `livemode`, *rollback* em falha; (3) **com Stripe real** — pagamento: clique duplo, chaves diferentes, 6 requisições simultâneas, falha do Stripe (chave inválida), idempotência do próprio Stripe e a API ponta a ponta. Os testes usam o banco `loja_test`, esvaziado a cada teste; a suíte recusa rodar se for igual ao banco da loja. O "espião" de chamadas apenas conta e **repassa** ao Stripe real.

## Consequências

- + A concorrência é testada com *threads* e conexões reais, não simulada.
- + Os níveis puros rodam em qualquer lugar; os demais pulam sozinhos sem chaves (Stripe).
- − Os testes de pagamento dependem de rede e de chaves.
- − Os testes de MySQL dependem de um servidor local.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Testes baseados em propriedades (Hypothesis) | Explorariam estados não previstos; a enumeração de permutações já cobre o espaço pequeno. |
| Testes de contrato (Pact) | Excessivo para um único consumidor. |
| SQLite em memória nos testes | Não reproduz as travas nem o erro 1062 do MySQL, que são o objeto do teste. |
| Mocks do SDK do Stripe | Contraria o [ADR-0008](0008-stripe-somente-em-modo-de-teste.md). |

## Referências

- `backend/tests/`
- `backend/pytest.ini` (marcador `stripe`)

## Relacionados

[ADR-0008](0008-stripe-somente-em-modo-de-teste.md)
