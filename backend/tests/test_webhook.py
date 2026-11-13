import threading

from app import services
from app.db import connect
from tests.events import evento


def estado(conn, pedido_id):
    return services.get_order(conn, pedido_id)["status"]


def total_eventos(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM webhook_events").fetchone()["n"]


def test_mesmo_webhook_tres_vezes_muda_o_pedido_uma_vez(conn, pedido):
    ev = evento("pago", pedido.id, pedido.pi, pedido.total)
    resultados = [services.process_webhook(conn, ev).outcome for _ in range(3)]
    assert resultados == ["applied", "duplicate", "duplicate"]
    historico = services.get_order(conn, pedido.id)["history"]
    assert [h["to_status"] for h in historico] == ["pendente", "pago"]   # uma única transição
    assert total_eventos(conn) == 1


def test_oito_reenvios_simultaneos_aplicam_uma_vez(settings, conn, pedido):
    ev = evento("pago", pedido.id, pedido.pi, pedido.total)
    resultados, lock = [], threading.Lock()

    def worker():
        c = connect(settings)             # cada thread, sua própria conexão MySQL
        try:
            r = services.process_webhook(c, ev).outcome
        finally:
            c.close()
        with lock:
            resultados.append(r)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(resultados) == ["applied"] + ["duplicate"] * 7
    assert estado(conn, pedido.id) == "pago"


def test_pago_depois_de_estornado_continua_estornado(conn, pedido):
    pago = evento("pago", pedido.id, pedido.pi, pedido.total)
    estorno = evento("estornado", pedido.id, pedido.pi, pedido.total)
    assert services.process_webhook(conn, estorno).outcome == "applied"   # chegou ANTES do pago
    assert services.process_webhook(conn, pago).outcome == "ignored"      # o pago atrasado não ressuscita
    assert estado(conn, pedido.id) == "estornado"


def test_pago_estornado_na_ordem_normal(conn, pedido):
    services.process_webhook(conn, evento("pago", pedido.id, pedido.pi, pedido.total))
    services.process_webhook(conn, evento("estornado", pedido.id, pedido.pi, pedido.total))
    assert estado(conn, pedido.id) == "estornado"


def test_recusado_atrasado_nao_derruba_pedido_pago(conn, pedido):
    services.process_webhook(conn, evento("pago", pedido.id, pedido.pi, pedido.total))
    r = services.process_webhook(conn, evento("recusado", pedido.id, pedido.pi, pedido.total))
    assert r.outcome == "ignored" and estado(conn, pedido.id) == "pago"


def test_estorno_acha_o_pedido_pelo_payment_intent(conn, pedido):
    ev = evento("estornado", pedido.id, pedido.pi, pedido.total)
    assert "metadata" not in ev["data"]["object"]
    assert services.process_webhook(conn, ev).order_id == pedido.id


def test_evento_de_tipo_desconhecido_e_registrado_e_nao_altera_nada(conn, pedido):
    ev = {"id": "evt_x", "type": "customer.created", "livemode": False, "data": {"object": {"id": "cus_1"}}}
    assert services.process_webhook(conn, ev).outcome == "unrelated"
    assert services.process_webhook(conn, ev).outcome == "duplicate"
    assert estado(conn, pedido.id) == "pendente"


def test_evento_de_pedido_inexistente_nao_quebra(conn):
    ev = evento("pago", "ord_nao_existe", "pi_desconhecido", 100)
    assert services.process_webhook(conn, ev).outcome == "unknown_order"


def test_evento_de_producao_e_recusado(conn, pedido):
    ev = evento("pago", pedido.id, pedido.pi, pedido.total)
    ev["livemode"] = True
    try:
        services.process_webhook(conn, ev)
        assert False, "deveria recusar livemode=true"
    except services.MalformedEvent:
        pass
    assert estado(conn, pedido.id) == "pendente" and total_eventos(conn) == 0


def test_falha_no_meio_nao_marca_evento_como_processado(conn, pedido, monkeypatch):
    ev = evento("pago", pedido.id, pedido.pi, pedido.total)
    original = services._apply_transition

    def quebra(*args, **kwargs):
        raise RuntimeError("queda no meio do processamento")

    monkeypatch.setattr(services, "_apply_transition", quebra)
    try:
        services.process_webhook(conn, ev)
    except RuntimeError:
        pass
    assert estado(conn, pedido.id) == "pendente"
    assert total_eventos(conn) == 0                                  # ROLLBACK total, inclusive do INSERT do evento

    monkeypatch.setattr(services, "_apply_transition", original)     # o Stripe reenvia...
    assert services.process_webhook(conn, ev).outcome == "applied"   # ...e agora funciona
