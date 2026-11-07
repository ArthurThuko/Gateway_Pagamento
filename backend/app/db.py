import re
from contextlib import contextmanager
from datetime import datetime, timezone

import pymysql
from pymysql.cursors import DictCursor

DUPLICATE_KEY = 1062
_ENGINE = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS products (
        id VARCHAR(64) NOT NULL PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        price_cents INT NOT NULL,
        CONSTRAINT ck_products_preco CHECK (price_cents > 0)
    ) {_ENGINE}""",
    f"""CREATE TABLE IF NOT EXISTS orders (
        id VARCHAR(40) NOT NULL PRIMARY KEY,
        status VARCHAR(20) NOT NULL,
        total_cents INT NOT NULL,
        currency CHAR(3) NOT NULL DEFAULT 'brl',
        payment_intent_id VARCHAR(100) NULL,
        client_secret VARCHAR(255) NULL,
        created_at VARCHAR(40) NOT NULL,
        updated_at VARCHAR(40) NOT NULL,
        UNIQUE KEY uq_orders_payment_intent (payment_intent_id),   -- no máximo UM PaymentIntent por pedido
        KEY ix_orders_created (created_at)
    ) {_ENGINE}""",
    f"""CREATE TABLE IF NOT EXISTS order_items (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        order_id VARCHAR(40) NOT NULL,
        product_id VARCHAR(64) NOT NULL,
        name VARCHAR(120) NOT NULL,
        unit_price_cents INT NOT NULL,
        quantity INT NOT NULL,
        CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders (id)
    ) {_ENGINE}""",
    f"""CREATE TABLE IF NOT EXISTS idempotency_keys (
        idem_key VARCHAR(200) NOT NULL PRIMARY KEY,
        order_id VARCHAR(40) NOT NULL,
        state VARCHAR(12) NOT NULL,
        response_json TEXT NULL,
        created_epoch BIGINT NOT NULL,
        KEY ix_idem_order (order_id)
    ) {_ENGINE}""",
    # Um webhook (event.id) só é processado uma vez: a PRIMARY KEY é a trava.
    f"""CREATE TABLE IF NOT EXISTS webhook_events (
        event_id VARCHAR(100) NOT NULL PRIMARY KEY,
        event_type VARCHAR(100) NOT NULL,
        order_id VARCHAR(40) NULL,
        outcome VARCHAR(20) NOT NULL,
        received_at VARCHAR(40) NOT NULL
    ) {_ENGINE}""",
    # Trilha de auditoria: cada mudança de estado e o que a causou.
    f"""CREATE TABLE IF NOT EXISTS order_history (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        order_id VARCHAR(40) NOT NULL,
        from_status VARCHAR(20) NULL,
        to_status VARCHAR(20) NOT NULL,
        cause VARCHAR(40) NOT NULL,
        event_id VARCHAR(100) NULL,
        occurred_at VARCHAR(40) NOT NULL,
        KEY ix_hist_order (order_id)
    ) {_ENGINE}""",
]

PRODUTOS = [
    ("camiseta", "Camiseta de algodão", 7990),
    ("caneca", "Caneca de cerâmica", 3490),
    ("mochila", "Mochila urbana", 15900),
    ("adesivos", "Kit de adesivos", 1990),
]


class Conexao:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        cur = self.raw.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, linhas):
        cur = self.raw.cursor()
        cur.executemany(sql, linhas)
        return cur

    def close(self):
        self.raw.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def is_duplicate(exc: BaseException) -> bool:
    return isinstance(exc, pymysql.err.IntegrityError) and bool(exc.args) and exc.args[0] == DUPLICATE_KEY


def _raw_connect(s, database=None):
    return pymysql.connect(host=s.mysql_host, port=s.mysql_port, user=s.mysql_user, password=s.mysql_password,
                           database=database, charset="utf8mb4", cursorclass=DictCursor,
                           autocommit=True, connect_timeout=10)


def connect(settings) -> Conexao:
    return Conexao(_raw_connect(settings, settings.mysql_database))


def seed_products(conn: Conexao) -> None:
    for pid, nome, preco in PRODUTOS:
        conn.execute("INSERT IGNORE INTO products (id, name, price_cents) VALUES (%s, %s, %s)", (pid, nome, preco))


def init_db(settings) -> None:
    nome = settings.mysql_database
    if not re.fullmatch(r"[A-Za-z0-9_]+", nome):
        raise RuntimeError("MYSQL_DATABASE deve conter apenas letras, números e _")
    try:
        raw = _raw_connect(settings)
    except pymysql.err.OperationalError as exc:
        raise RuntimeError(
            f"Não foi possível conectar ao MySQL em {settings.mysql_host}:{settings.mysql_port} ({exc}). "
            "Suba o banco com `docker compose up -d` e confira as variáveis MYSQL_* no .env."
        ) from exc
    try:
        raw.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{nome}` CHARACTER SET utf8mb4")
    finally:
        raw.close()
    conn = connect(settings)
    try:
        for ddl in SCHEMA:
            conn.execute(ddl)
        seed_products(conn)
    finally:
        conn.close()


@contextmanager
def transaction(conn: Conexao):
    """BEGIN ... COMMIT; qualquer exceção desfaz tudo (ROLLBACK)."""
    conn.raw.begin()
    try:
        yield conn
    except BaseException:
        conn.raw.rollback()
        raise
    else:
        conn.raw.commit()
