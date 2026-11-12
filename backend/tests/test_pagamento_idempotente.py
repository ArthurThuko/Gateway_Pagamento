import threading
import uuid

import pytest
import stripe

from app import services
from app.db import connect
from app.gateway import StripeGateway
from tests.events import evento


@pytest.fixture
def ordem(conn):
    return services.create_order(conn, [{"product_id": "caneca", "quantity": 1}])


@pytest.mark.stripe
def test_clique_duplo_com_mesma_chave_cria_um_unico_pagamento(conn, gateway, ordem):
    a = services.pay_order(conn, gateway, ordem["id"], "chave-1")
    b = services.pay_order(conn, gateway, ordem["id"], "chave-1")
    assert a.body == b.body
    assert (a.replayed, b.replayed) == (False, True)
    assert gateway.calls == 1                          # o 2º clique nem chegou ao Stripe


@pytest.mark.stripe
def test_pagamento_no_stripe_tem_valor_e_metadata_corretos(conn, settings, gateway, ordem):
    pago = services.pay_order(conn, gateway, ordem["id"], "chave-1").body
    pi = stripe.PaymentIntent.retrieve(pago["payment_intent_id"], api_key=settings.stripe_secret_key)
    assert pi.amount == ordem["total_cents"] and pi.currency == "brl"
    assert pi.metadata["order_id"] == ordem["id"]


@pytest.mark.stripe
def test_chaves_diferentes_no_mesmo_pedido_reaproveitam_o_pagamento(conn, gateway, ordem):
    a = services.pay_order(conn, gateway, ordem["id"], "chave-1")
    b = services.pay_order(conn, gateway, ordem["id"], "chave-2")
    assert a.body["payment_intent_id"] == b.body["payment_intent_id"]
    assert gateway.calls == 1


@pytest.mark.stripe
def test_mesma_chave_em_outro_pedido_e_rejeitada(conn, gateway, ordem):
    outra = services.create_order(conn, [{"product_id": "caneca", "quantity": 1}])
    services.pay_order(conn, gateway, ordem["id"], "chave-1")
    with pytest.raises(services.IdempotencyConflict):
        services.pay_order(conn, gateway, outra["id"], "chave-1")


@pytest.mark.stripe
def test_pedido_pago_nao_aceita_novo_pagamento(conn, gateway, ordem):
    pi = services.pay_order(conn, gateway, ordem["id"], "chave-1").body["payment_intent_id"]
    services.process_webhook(conn, evento("pago", ordem["id"], pi, ordem["total_cents"]))
    with pytest.raises(services.NotPayable):
        services.pay_order(conn, gateway, ordem["id"], "outra-chave")


@pytest.mark.stripe
def test_falha_do_stripe_libera_a_chave_para_nova_tentativa(conn, gateway, ordem):
    ruim = StripeGateway("sk_test_chave_invalida")     # o Stripe real responde 401
    with pytest.raises(services.GatewayUnavailable):
        services.pay_order(conn, ruim, ordem["id"], "chave-1")
    assert conn.execute("SELECT COUNT(*) AS n FROM idempotency_keys").fetchone()["n"] == 0
    assert services.pay_order(conn, gateway, ordem["id"], "chave-1").body["payment_intent_id"]


@pytest.mark.stripe
def test_cliques_simultaneos_nunca_geram_duas_cobrancas(settings, conn, gateway, ordem):
    resultados, lock = [], threading.Lock()

    def worker(chave):
        c = connect(settings)
        try:
            r = services.pay_order(c, gateway, ordem["id"], chave).body["payment_intent_id"]
        except services.RequestInProgress:
            r = "em-andamento"
        finally:
            c.close()
        with lock:
            resultados.append(r)

    # 3 requisições com a MESMA chave e 3 com chaves diferentes, todas ao mesmo tempo
    threads = [threading.Thread(target=worker, args=(f"chave-{i % 4}",)) for i in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert gateway.calls == 1
    pagamentos = {r for r in resultados if r != "em-andamento"}
    assert len(pagamentos) == 1


@pytest.mark.stripe
def test_stripe_deduplica_a_criacao_pela_idempotency_key(stripe_gateway):
    chave = f"teste-{uuid.uuid4().hex}"
    a = stripe_gateway.create_payment(order_id="ord_teste", amount_cents=1000, currency="brl", idempotency_key=chave)
    b = stripe_gateway.create_payment(order_id="ord_teste", amount_cents=1000, currency="brl", idempotency_key=chave)
    assert a.id == b.id


def test_preco_vem_do_banco_e_nao_do_cliente(conn):
    ordem = services.create_order(conn, [{"product_id": "camiseta", "quantity": 2}, {"product_id": "camiseta", "quantity": 1}])
    assert ordem["total_cents"] == 3 * 7990
    with pytest.raises(services.InvalidOrder):
        services.create_order(conn, [{"product_id": "inexistente", "quantity": 1}])
