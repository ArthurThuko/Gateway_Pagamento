"""Ponta a ponta pela API HTTP, com MySQL e Stripe REAL em modo de teste (precisa de rede e chaves no .env).

Os webhooks aqui são assinados com o segredo de teste da suíte; o que o Stripe entrega de verdade é
exercitado pela demonstração (scripts/demo_webhooks.py).
"""
import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

pytestmark = pytest.mark.stripe

from app.signature import sign_payload  # noqa: E402
from tests.events import evento  # noqa: E402


@pytest.fixture
def client(settings, stripe_gateway):
    from fastapi.testclient import TestClient
    from app.main import create_app
    return TestClient(create_app(settings, stripe_gateway))


@pytest.fixture
def pedido_api(client, conn):
    ordem = client.post("/orders", json={"items": [{"product_id": "camiseta", "quantity": 1}]}).json()
    pay = client.post(f"/orders/{ordem['id']}/pay", headers={"Idempotency-Key": "k-1"}).json()
    return ordem, pay["payment_intent_id"]


def enviar(client, ev, segredo):
    corpo = json.dumps(ev).encode()
    return client.post("/webhooks/stripe", content=corpo,
                       headers={"Stripe-Signature": sign_payload(corpo, segredo), "Content-Type": "application/json"})


def status_do_pedido(client, pedido_id):
    return client.get(f"/orders/{pedido_id}").json()["status"]


def test_pagar_exige_idempotency_key(client, pedido_api):
    assert client.post(f"/orders/{pedido_api[0]['id']}/pay").status_code == 400


def test_clique_duplo_devolve_a_mesma_resposta(client, pedido_api):
    ordem, pi = pedido_api
    r = client.post(f"/orders/{ordem['id']}/pay", headers={"Idempotency-Key": "k-1"})
    assert r.status_code == 200 and r.json()["payment_intent_id"] == pi
    assert r.headers["Idempotent-Replayed"] == "true"


def test_webhook_assinado_marca_pedido_como_pago(client, settings, pedido_api):
    ordem, pi = pedido_api
    r = enviar(client, evento("pago", ordem["id"], pi, ordem["total_cents"]), settings.webhook_secret)
    assert r.status_code == 200 and r.json()["outcome"] == "applied"
    assert status_do_pedido(client, ordem["id"]) == "pago"


def test_mesmo_webhook_cinco_vezes_responde_200_e_aplica_uma_vez(client, settings, pedido_api):
    ordem, pi = pedido_api
    ev = evento("pago", ordem["id"], pi, ordem["total_cents"])
    respostas = [enviar(client, ev, settings.webhook_secret) for _ in range(5)]
    assert [r.status_code for r in respostas] == [200] * 5          # 200 sempre: o Stripe para de reenviar
    assert [r.json()["outcome"] for r in respostas] == ["applied"] + ["duplicate"] * 4
    assert len(client.get(f"/orders/{ordem['id']}").json()["history"]) == 2


def test_webhook_com_assinatura_falsa_e_rejeitado(client, pedido_api):
    ordem, pi = pedido_api
    r = enviar(client, evento("pago", ordem["id"], pi, ordem["total_cents"]), "whsec_do_atacante")
    assert r.status_code == 400
    assert status_do_pedido(client, ordem["id"]) == "pendente"


def test_webhook_sem_cabecalho_de_assinatura_e_rejeitado(client, pedido_api):
    ordem, pi = pedido_api
    corpo = json.dumps(evento("pago", ordem["id"], pi, 1)).encode()
    assert client.post("/webhooks/stripe", content=corpo).status_code == 400


def test_pago_depois_de_estornado_pela_api(client, settings, pedido_api):
    ordem, pi = pedido_api
    enviar(client, evento("estornado", ordem["id"], pi, ordem["total_cents"]), settings.webhook_secret)
    r = enviar(client, evento("pago", ordem["id"], pi, ordem["total_cents"]), settings.webhook_secret)
    assert r.status_code == 200 and r.json()["outcome"] == "ignored"
    assert status_do_pedido(client, ordem["id"]) == "estornado"


def test_enviar_so_depois_de_pago(client, settings, pedido_api):
    ordem, pi = pedido_api
    assert client.post(f"/orders/{ordem['id']}/ship").status_code == 409
    enviar(client, evento("pago", ordem["id"], pi, ordem["total_cents"]), settings.webhook_secret)
    assert client.post(f"/orders/{ordem['id']}/ship").json()["status"] == "enviado"
