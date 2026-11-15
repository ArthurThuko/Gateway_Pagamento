# ADR-0004 — Verificação manual da assinatura HMAC-SHA256 sobre o corpo bruto

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

O endpoint do webhook é público: qualquer pessoa pode enviar um `POST` dizendo "pagamento aprovado". É preciso provar que a mensagem veio do Stripe e não foi alterada.

## Decisão

O Stripe envia `Stripe-Signature: t=<timestamp>,v1=<hex>`, com `v1 = HMAC_SHA256(segredo, "<timestamp>." + corpo)`. `verify_signature`: recebe o corpo como **bytes**, exatamente como chegou (o JSON só é lido **depois** de a assinatura passar); recalcula o HMAC com `STRIPE_WEBHOOK_SECRET`; compara em **tempo constante** (`hmac.compare_digest`); aceita **várias** assinaturas `v1` (rotação de segredo); rejeita timestamps com mais de **5 minutos** de diferença (anti-*replay*). A implementação é própria, no mesmo formato do Stripe.

## Consequências

- + Sem o segredo, é inviável produzir assinatura válida para um corpo escolhido.
- + Usar os bytes brutos evita o erro clássico de reserializar o JSON.
- + O timestamp na conta impede reaproveitar um webhook verdadeiro capturado antes.
- + Implementação curta, testável e defensável em apresentação.
- − Mantemos código de segurança próprio; em produção convém avaliar a função oficial.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| `stripe.Webhook.construct_event` | Menos código e mantido pelo Stripe; seria a escolha prática em produção. Descartada aqui para explicitar o mecanismo pedido no desafio. |
| Lista de IPs do Stripe | Os IPs mudam e não provam a integridade do corpo. Pode ser camada adicional. |
| Token secreto na URL | Vaza em *logs* e não autentica o conteúdo. |
| Buscar o evento na API do Stripe pelo `id` | Dispensa o segredo, mas exige uma chamada por evento. Possível complemento antifraude. |

## Referências

- `backend/app/signature.py`
- `backend/app/main.py` → `deliver`
- `tests/test_signature.py`
- [SPEC-002](../specs/SPEC-002-webhook-stripe.md)

## Relacionados

[ADR-0001](0001-webhook-como-fonte-da-verdade.md), [ADR-0008](0008-stripe-somente-em-modo-de-teste.md)
