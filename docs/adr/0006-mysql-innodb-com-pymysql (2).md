# ADR-0006 — MySQL 8 (InnoDB) com PyMySQL e SQL explícito

- **Status:** Aceito
- **Data:** 2026-11-13

## Contexto

As garantias dos [ADR-0002](0002-prevencao-de-cobranca-duplicada.md) e [ADR-0003](0003-deduplicacao-de-webhook-por-insert.md) dependem de transações, restrições de unicidade e travas por linha. O MySQL foi o banco exigido pela equipe. A primeira versão do projeto usou SQLite (`BEGIN IMMEDIATE`, trava global de escrita) e foi migrada.

## Decisão

MySQL 8.0.16+ com InnoDB e `utf8mb4`. Driver **PyMySQL** (Python puro; `cryptography` para a autenticação `caching_sha2_password`). Camada fina em `db.py` (`Conexao`, `transaction()`, `is_duplicate`) e **SQL explícito** em `services.py`, sempre parametrizado (`%s`). Uma conexão por requisição. O banco e as tabelas são criados por `init_db`. A trava global do SQLite virou **trava por pedido** (`FOR UPDATE`) e a deduplicação passou a depender do `INSERT` em chave primária.

## Consequências

- + Três comportamentos do InnoDB ficam visíveis no código: `INSERT` duplicado espera e falha com 1062; `FOR UPDATE` trava a linha; `UNIQUE` aceita vários `NULL`.
- + Poucas dependências.
- − Mais SQL escrito à mão e sem migrações automáticas.
- − Sem *pool* de conexões (uma conexão por requisição).
- − Código acoplado ao dialeto MySQL.

## Alternativas consideradas

| Alternativa | Por que não foi a escolhida |
|---|---|
| SQLAlchemy Core (`text()`) | Dá *pool* e transações prontas mantendo as travas visíveis; é o caminho de menor esforço se o projeto crescer. O PyMySQL continuaria como driver por baixo. |
| SQLAlchemy ORM | Modelos e relacionamentos, mas esconde `FOR UPDATE` e o momento do `INSERT` (`flush`), que são o objeto da demonstração. |
| Alembic (migrações) | Útil quando o esquema evoluir em produção; desnecessário para um esquema pequeno criado por `init_db`. |
| SQLite | Zero configuração, mas com trava global; foi a primeira versão. Fora dos requisitos. |
| PostgreSQL | `INSERT … ON CONFLICT` e `SKIP LOCKED`; seria boa escolha sem a restrição de usar MySQL. |
| Driver assíncrono (aiomysql, asyncmy) | Complica transações e testes sem necessidade nesta escala. |

## Referências

- `backend/app/db.py`
- `backend/app/services.py`
- [02 — Banco de dados](../02-banco-de-dados.md)

## Relacionados

[ADR-0002](0002-prevencao-de-cobranca-duplicada.md), [ADR-0003](0003-deduplicacao-de-webhook-por-insert.md)
