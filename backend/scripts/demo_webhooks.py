"""Demonstração com o STRIPE REAL em modo de teste: 5 reenvios, assinatura falsa e ordem trocada.

Pré-requisitos: API rodando, MySQL no ar, chaves de teste no .env e o `stripe listen` PARADO.
(Se o `stripe listen` estiver ligado, o Stripe entrega os eventos antes do script e o 1º envio já aparece
como "duplicate".)

O que o script faz:
  1. cria pedidos e pagamentos pela nossa API (PaymentIntents reais no Stripe de teste);
  2. confirma o pagamento com cartões de teste pela API do Stripe (e estorna um deles);
  3. busca os eventos REAIS gerados pelo Stripe (payment_intent.succeeded, charge.refunded);
  4. entrega esses eventos ao nosso webhook, assinados com STRIPE_WEBHOOK_SECRET. Para o endpoint isso é
     indistinguível de uma entrega do Stripe: a verificação é a mesma conta HMAC-SHA256.

Uso:  python scripts/demo_webhooks.py            (Windows: py scripts\\demo_webhooks.py)
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stripe  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.signature import sign_payload  # noqa: E402

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
CFG = load_settings()
CFG.validate_stripe()
stripe.api_key = CFG.stripe_secret_key


def http(metodo, caminho, corpo=None, headers=None):
    dados = corpo if isinstance(corpo, bytes) else (json.dumps(corpo).encode() if corpo is not None else None)
    req = urllib.request.Request(API + caminho, data=dados, method=metodo,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def titulo(texto):
    print(f"\n{'=' * 72}\n{texto}\n{'=' * 72}")


def novo_pedido():
    """Pedido + PaymentIntent real (criado pela nossa API, com Idempotency-Key)."""
    _, ordem = http("POST", "/orders", {"items": [{"product_id": "camiseta", "quantity": 1}]})
    _, pay = http("POST", f"/orders/{ordem['id']}/pay", headers={"Idempotency-Key": f"demo-{ordem['id']}"})
    return ordem, pay["payment_intent_id"]


def confirmar_no_stripe(pi):
    """Paga com o cartão de teste 4242 4242 4242 4242 (pm_card_visa)."""
    stripe.PaymentIntent.confirm(pi, payment_method="pm_card_visa", return_url="https://example.com/retorno")


def _dict(obj):
    """Converte objetos do SDK do Stripe (que nas versões novas NÃO são dict) em dict puro."""
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()
    return json.loads(json.dumps(obj, default=lambda o: o.to_dict() if hasattr(o, "to_dict") else dict(o)))


def evento_real(tipo, pi, tentativas=20):
    """Espera o Stripe registrar o evento e devolve o JSON real dele."""
    for _ in range(tentativas):
        for ev in stripe.Event.list(type=tipo, limit=50).data:
            d = _dict(ev)
            obj = d["data"]["object"]
            ligado_ao_pi = obj.get("id") == pi if obj.get("object") == "payment_intent" else obj.get("payment_intent") == pi
            if ligado_ao_pi:
                return d
        time.sleep(1.5)
    raise SystemExit(f"O Stripe não registrou {tipo} para {pi} a tempo.")


def enviar(evento, segredo=None):
    corpo = json.dumps(evento).encode()
    return http("POST", "/webhooks/stripe", corpo,
                {"Stripe-Signature": sign_payload(corpo, segredo or CFG.webhook_secret)})


def mostrar_pedido(pedido_id):
    p = http("GET", f"/orders/{pedido_id}")[1]
    caminho = " -> ".join(h["to_status"] for h in p["history"])
    print(f"  Estado do pedido: {p['status'].upper()}   (histórico: {caminho})")


titulo("1) Mesmo webhook (payment_intent.succeeded REAL do Stripe) enviado 5 vezes")
ordem, pi = novo_pedido()
confirmar_no_stripe(pi)
ev = evento_real("payment_intent.succeeded", pi)
print(f"  Pedido {ordem['id']}  |  PaymentIntent {pi}  |  evento {ev['id']}")
for i in range(1, 6):
    status, corpo = enviar(ev)
    print(f"  Envio {i}: HTTP {status}  outcome={corpo['outcome']:<10} {corpo['detail']}")
mostrar_pedido(ordem["id"])

titulo("2) Webhook com assinatura FALSA (segredo do atacante)")
ordem2, pi2 = novo_pedido()
confirmar_no_stripe(pi2)
ev2 = evento_real("payment_intent.succeeded", pi2)
status, corpo = enviar(ev2, segredo="whsec_segredo_do_atacante")
print(f"  Corpo idêntico ao do Stripe, assinatura falsa -> HTTP {status}  {corpo['detail']}")
mostrar_pedido(ordem2["id"])
status, corpo = enviar(ev2)
print(f"  Mesmo corpo, assinatura correta               -> HTTP {status}  outcome={corpo['outcome']}")
mostrar_pedido(ordem2["id"])

titulo("3) 'Pago' chega DEPOIS de 'estornado' (eventos reais, entregues invertidos)")
ordem3, pi3 = novo_pedido()
confirmar_no_stripe(pi3)
ev_pago = evento_real("payment_intent.succeeded", pi3)
stripe.Refund.create(payment_intent=pi3)
ev_estorno = evento_real("charge.refunded", pi3)
for rotulo, e in (("estornado", ev_estorno), ("pago (atrasado)", ev_pago)):
    status, corpo = enviar(e)
    print(f"  {rotulo:<16}: HTTP {status}  outcome={corpo['outcome']:<8} {corpo['detail']}")
mostrar_pedido(ordem3["id"])
print()