# ADR-0008 — Somente Stripe em modo de teste, sem gateway simulado

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

É preciso evitar cobrança real por engano e garantir que a demonstração e os testes de pagamento usem o gateway verdadeiro. A primeira versão tinha um gateway simulado, removido por decisão da equipe.

## Decisão

A configuração exige `sk_test_`, `pk_test_` e `whsec_` e a API **não sobe** sem elas; eventos `livemode: true` são recusados. Não existe gateway simulado: os testes de webhook, assinatura e estados usam payloads no formato do Stripe como **dado de entrada** (`tests/events.py`), e tudo que cria pagamento fala com o Stripe real de teste (pulado se faltarem chaves).

## Consequências

- + Demonstração e testes exercitam o comportamento real do Stripe, inclusive sua idempotência.
- + Impossível cobrar de verdade por engano.
- − Testes de pagamento precisam de rede e de chaves.
- − Mais lentos que testes com simulação.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| Gateway simulado (`FakeGateway`) | Rápido e offline, mas contraria a decisão da equipe e mascara comportamentos reais. Seria adequado para CI sem segredos. |
| `stripe-mock` (servidor oficial) | Fiel ao esquema da API, mas não replica a idempotência real nem os eventos. |
| Gravar e reproduzir respostas (VCR) | Determinístico, porém as gravações envelhecem. |
| Mock do SDK (`unittest.mock`) | Não valida a integração. |

## Referências

- `backend/app/config.py` → `validate_stripe`
- `backend/app/gateway.py`
- `backend/app/services.py` → `_validate` (`livemode`)
- `tests/events.py`

## Relacionados

[ADR-0004](0004-assinatura-hmac-do-webhook.md), [ADR-0013](0013-estrategia-de-testes.md)
