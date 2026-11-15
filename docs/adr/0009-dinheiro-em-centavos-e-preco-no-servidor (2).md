# ADR-0009 — Dinheiro em centavos inteiros e preço decidido pelo servidor

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

Valores monetários exigem exatidão, e o navegador não é confiável para informar preços.

## Decisão

Todos os valores são **inteiros em centavos** (`INT`). `POST /orders` aceita apenas `product_id` e quantidade (1 a 99); o total é calculado a partir de `products`. Nome e preço unitário são **copiados** para `order_items`.

## Consequências

- + Sem erro de arredondamento; o Stripe também usa a menor unidade da moeda.
- + Impede adulteração de preço pelo cliente.
- + O pedido é um registro histórico, imune a mudanças futuras do catálogo.
- − Formatação para reais fica a cargo da interface.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| `float` | Erros de arredondamento. |
| `Decimal` | Funciona, mas o Stripe já usa inteiros: converter só acrescenta risco. |
| Preço enviado pelo cliente | Permitiria comprar por R$ 0,01. |

## Referências

- `backend/app/services.py` → `create_order`
- [02 — Banco de dados](../02-banco-de-dados.md)

## Relacionados

[ADR-0006](0006-mysql-innodb-com-pymysql.md)
