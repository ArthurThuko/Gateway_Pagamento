# SPEC-002 — Webhook do Stripe (`POST /webhooks/stripe`)

- **Status:** Vigente
- **Decisões relacionadas:** [ADR-0001](../adr/0001-webhook-como-fonte-da-verdade.md), [ADR-0003](../adr/0003-deduplicacao-de-webhook-por-insert.md), [ADR-0004](../adr/0004-assinatura-hmac-do-webhook.md), [ADR-0008](../adr/0008-stripe-somente-em-modo-de-teste.md), [ADR-0011](../adr/0011-processamento-sincrono-do-webhook.md)
- **Implementação:** `backend/app/main.py` → `stripe_webhook`, `deliver`; `backend/app/signature.py`; `backend/app/services.py` → `process_webhook`

## 1. Objetivo

Receber as notificações do Stripe, **autenticá-las**, processar cada evento **no máximo uma vez** e aplicar a mudança de estado do pedido, mesmo com reenvios, duplicidade e ordem trocada.

## 2. Requisição

| Item | Regra |
|---|---|
| Método e rota | `POST /webhooks/stripe` |
| Header `Stripe-Signature` | `t=<timestamp>,v1=<hex>[,v1=<hex>…]` |
| Corpo | JSON do evento do Stripe, lido como **bytes brutos** |

## 3. Autenticação (antes de qualquer outra coisa)

Computa-se `esperada = HMAC_SHA256(STRIPE_WEBHOOK_SECRET, "<t>." + corpo_bruto)` em hexadecimal.

O webhook é **rejeitado** (`400`) se:

| Condição | Mensagem de `detail` |
|---|---|
| Header ausente | cabeçalho Stripe-Signature ausente |
| Sem `t` ou sem nenhum `v1`, ou `t` não numérico | cabeçalho em formato inválido / timestamp inválido |
| Nenhum `v1` confere com `esperada` (comparação em **tempo constante**) | assinatura não confere |
| `abs(agora − t)` maior que `WEBHOOK_TOLERANCE_SECONDS` (padrão **300 s**) | timestamp fora da tolerância (possível replay) |

Só **depois** de autenticado o corpo é interpretado como JSON (JSON inválido → `400`). Nunca se reserializa o corpo antes de verificar.

## 4. Validação do evento

Um evento é aceito se for um objeto com `id` (texto), `type` (texto) e `data.object` (objeto). Caso contrário → `400`. Eventos com `livemode: true` → `400` (somente modo de teste).

## 5. Mapeamento evento do Stripe → evento do domínio

| `type` do Stripe | Evento do domínio | Observação |
|---|---|---|
| `payment_intent.succeeded` | `pagamento_confirmado` | Pedido por `metadata.order_id`, com *fallback* por `data.object.id` (= `payment_intent_id`) |
| `payment_intent.payment_failed` | `pagamento_recusado` | Idem |
| `charge.refunded` com `refunded: true` | `pagamento_estornado` | Pedido por `metadata.order_id`, com *fallback* por `data.object.payment_intent`. Estorno **parcial** (`refunded` ≠ `true`) cai em `unrelated` |
| Qualquer outro | — | `unrelated` |

## 6. Processamento (uma transação)

1. `INSERT` em `webhook_events` (`event_id`, `event_type`, `outcome = processing`). Chave duplicada (erro 1062) → resultado `duplicate` e fim.
2. Tipo não mapeado → grava `outcome = unrelated`; fim.
3. `SELECT … FROM orders … FOR UPDATE` (por `metadata.order_id`; se não houver, por `payment_intent_id`). Pedido inexistente → `outcome = unknown_order`; fim.
4. `decide(estado_atual, evento)` ([SPEC-003](SPEC-003-maquina-de-estados.md)). Se aplicável: `UPDATE orders` e `INSERT order_history` (com `event_id`).
5. `UPDATE webhook_events` com `order_id` e `outcome` (`applied` ou `ignored`). `COMMIT`.

Qualquer exceção → `ROLLBACK` de **toda** a transação (inclusive o `INSERT` do passo 1); o evento **não** fica marcado como processado.

## 7. Respostas

**`200`** — corpo `{"outcome", "order_id", "status", "detail"}`:

| `outcome` | Quando | `order_id` / `status` |
|---|---|---|
| `applied` | A transição foi aplicada | preenchidos |
| `ignored` | O pedido existe, mas a máquina de estados não aceita o evento naquele estado | preenchidos (estado atual) |
| `duplicate` | `event_id` já processado | `null` |
| `unrelated` | Tipo que não altera pedidos | `null` |
| `unknown_order` | Nenhum pedido corresponde | `null` |

**`400`** — corpo `{"outcome": "rejected", "detail": "…"}`: assinatura inválida, JSON inválido, evento malformado ou `livemode: true`.

**`500`** — falha nossa (por exemplo, banco indisponível). **Intencional**: sem `200`, o Stripe reenvia.

> Regra de ouro: tudo que **não** é erro de autenticação ou de formato recebe `200`, para o Stripe parar de reenviar.

## 8. Invariantes

| # | Invariante | Garantida por |
|---|---|---|
| W1 | Um `event_id` altera o estado **no máximo uma vez** | PK de `webhook_events` e `INSERT` primeiro |
| W2 | Mudança de estado e registro do evento são **atômicos** | Transação única |
| W3 | Dois eventos do mesmo pedido são aplicados **um de cada vez** | `SELECT … FOR UPDATE` |
| W4 | Nada é gravado para um webhook com assinatura inválida | Verificação antes do processamento |
| W5 | A ordem de chegada não muda o estado final | [SPEC-003](SPEC-003-maquina-de-estados.md) |

## 9. Casos de aceite

| # | Dado / Quando / Então | Teste |
|---|---|---|
| W-A1 | Mesmo evento 3× → `applied`, `duplicate`, `duplicate`; uma transição no histórico | `test_mesmo_webhook_tres_vezes_muda_o_pedido_uma_vez` |
| W-A2 | 8 *threads* com o mesmo evento → um `applied` e sete `duplicate` | `test_oito_reenvios_simultaneos_aplicam_uma_vez` |
| W-A3 | `estornado` antes de `pago` → `pago` é `ignored`; pedido `estornado` | `test_pago_depois_de_estornado_continua_estornado` |
| W-A4 | `recusado` atrasado após `pago` → `ignored` | `test_recusado_atrasado_nao_derruba_pedido_pago` |
| W-A5 | Estorno sem `metadata` acha o pedido pelo `payment_intent` | `test_estorno_acha_o_pedido_pelo_payment_intent` |
| W-A6 | Tipo desconhecido → `unrelated`, depois `duplicate`; pedido intacto | `test_evento_de_tipo_desconhecido_e_registrado_e_nao_altera_nada` |
| W-A7 | Pedido inexistente → `unknown_order` | `test_evento_de_pedido_inexistente_nao_quebra` |
| W-A8 | `livemode: true` → recusado; nada gravado | `test_evento_de_producao_e_recusado` |
| W-A9 | Falha no meio → nada gravado; o reenvio é `applied` | `test_falha_no_meio_nao_marca_evento_como_processado` |
| W-A10 | Assinatura válida, segredo errado, corpo adulterado, replay, cabeçalho malformado, rotação | `tests/test_signature.py` |
| W-A11 | 5 reenvios pela API → `200` ×5, `applied` + 4 `duplicate` | `test_mesmo_webhook_cinco_vezes_responde_200_e_aplica_uma_vez` |
| W-A12 | Assinatura falsa pela API → `400`; pedido `pendente` | `test_webhook_com_assinatura_falsa_e_rejeitado` |
| W-A13 | Sem o header → `400` | `test_webhook_sem_cabecalho_de_assinatura_e_rejeitado` |
