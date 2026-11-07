import time
import uuid

TIPOS = ("pago", "recusado", "estornado")


def build_event(tipo: str, order_id: str, payment_intent_id: str, amount_cents: int) -> dict:
    pi = {"id": payment_intent_id, "object": "payment_intent", "amount": amount_cents,
          "currency": "brl", "metadata": {"order_id": order_id}}
    if tipo == "pago":
        nome, obj = "payment_intent.succeeded", {**pi, "status": "succeeded"}
    elif tipo == "recusado":
        nome, obj = "payment_intent.payment_failed", {**pi, "status": "requires_payment_method"}
    elif tipo == "estornado":
        nome, obj = "charge.refunded", {"id": f"ch_{uuid.uuid4().hex[:14]}", "object": "charge",
                                        "payment_intent": payment_intent_id, "amount": amount_cents,
                                        "amount_refunded": amount_cents, "refunded": True}
    else:
        raise ValueError(f"tipo desconhecido: {tipo}")
    return {"id": f"evt_{uuid.uuid4().hex[:24]}", "object": "event", "type": nome,
            "created": int(time.time()), "data": {"object": obj}}
