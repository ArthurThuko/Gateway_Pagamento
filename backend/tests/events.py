"""Monta payloads de webhook no formato do Stripe, como DADO DE ENTRADA dos testes de webhook.

Não é um gateway: nada aqui cria pagamentos nem fala com o Stripe. Serve para exercitar a nossa
lógica de recebimento com eventos controlados (duplicados, fora de ordem, etc.).
"""
import time
import uuid


def evento(tipo: str, order_id: str, payment_intent_id: str, amount_cents: int) -> dict:
    pi = {"id": payment_intent_id, "object": "payment_intent", "amount": amount_cents,
          "currency": "brl", "metadata": {"order_id": order_id}}
    if tipo == "pago":
        nome, obj = "payment_intent.succeeded", {**pi, "status": "succeeded"}
    elif tipo == "recusado":
        nome, obj = "payment_intent.payment_failed", {**pi, "status": "requires_payment_method"}
    elif tipo == "estornado":
        # Sem metadata de propósito: o pedido é localizado pelo payment_intent do charge.
        nome, obj = "charge.refunded", {"id": f"ch_{uuid.uuid4().hex[:14]}", "object": "charge",
                                        "payment_intent": payment_intent_id, "amount": amount_cents,
                                        "amount_refunded": amount_cents, "refunded": True}
    else:
        raise ValueError(f"tipo desconhecido: {tipo}")
    return {"id": f"evt_{uuid.uuid4().hex[:24]}", "object": "event", "type": nome, "livemode": False,
            "created": int(time.time()), "data": {"object": obj}}
