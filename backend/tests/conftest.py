import dataclasses
import os
import threading
import uuid
from types import SimpleNamespace

import pytest

from app import services
from app.config import load_settings
from app.db import connect, init_db
from app.gateway import StripeGateway

SEGREDO = "whsec_segredo_de_teste"
TABELAS = ("order_items", "order_history", "webhook_events", "idempotency_keys", "orders")


@pytest.fixture(scope="session")
def settings():
    """Usa o MySQL do .env, mas em um banco SEPARADO (MYSQL_TEST_DATABASE) para nunca tocar nos dados da loja."""
    base = load_settings()
    teste = os.environ.get("MYSQL_TEST_DATABASE", "loja_test")
    if teste == base.mysql_database:
        raise RuntimeError("MYSQL_TEST_DATABASE deve ser diferente de MYSQL_DATABASE.")
    s = dataclasses.replace(base, mysql_database=teste, webhook_secret=SEGREDO)
    init_db(s)
    return s


@pytest.fixture
def conn(settings):
    c = connect(settings)
    for tabela in TABELAS:       # banco limpo a cada teste (ordem respeita as chaves estrangeiras)
        c.execute(f"DELETE FROM {tabela}")
    yield c
    c.close()


@pytest.fixture
def pedido(conn):
    """Pedido pendente que já tem payment_intent_id, para os testes de WEBHOOK (que só precisam desse vínculo)."""
    ordem = services.create_order(conn, [{"product_id": "camiseta", "quantity": 2}])
    pi = f"pi_teste_{uuid.uuid4().hex[:18]}"
    conn.execute("UPDATE orders SET payment_intent_id = %s, client_secret = %s WHERE id = %s",
                 (pi, f"{pi}_secret_x", ordem["id"]))
    return SimpleNamespace(id=ordem["id"], pi=pi, total=ordem["total_cents"])


# ---------------------------------------------------------------- Stripe REAL (modo de teste)
@pytest.fixture
def stripe_gateway(settings):
    """Gateway de verdade. Sem chaves de teste no .env, os testes que dependem dele são pulados."""
    try:
        settings.validate_stripe()
    except RuntimeError as exc:
        pytest.skip(f"Stripe de teste não configurado no .env: {exc}")
    return StripeGateway(settings.stripe_secret_key)


class Espiao:
    """Conta as chamadas ao Stripe e REPASSA cada uma ao gateway real (não simula nada)."""

    def __init__(self, gateway):
        self._gateway = gateway
        self._lock = threading.Lock()
        self.calls = 0

    def create_payment(self, **kwargs):
        with self._lock:
            self.calls += 1
        return self._gateway.create_payment(**kwargs)


@pytest.fixture
def gateway(stripe_gateway):
    return Espiao(stripe_gateway)
