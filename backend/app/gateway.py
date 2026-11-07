from dataclasses import dataclass
from typing import Protocol

import stripe

stripe.max_network_retries = 2   # seguro: toda criação de pagamento leva Idempotency-Key


@dataclass(frozen=True)
class PaymentIntentResult:
    id: str
    client_secret: str
    status: str


class PaymentGateway(Protocol):
    def create_payment(self, *, order_id: str, amount_cents: int, currency: str,
                       idempotency_key: str) -> PaymentIntentResult: ...


class StripeGateway:
    def __init__(self, secret_key: str):
        if not secret_key.startswith("sk_test_"):
            raise RuntimeError("Por segurança, só chaves de TESTE (sk_test_...) são aceitas neste projeto.")
        self._key = secret_key

    def create_payment(self, *, order_id, amount_cents, currency, idempotency_key) -> PaymentIntentResult:
        pi = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            automatic_payment_methods={"enabled": True},
            metadata={"order_id": order_id},
            idempotency_key=idempotency_key,
            api_key=self._key,
        )
        return PaymentIntentResult(pi.id, pi.client_secret, pi.status)


def build_gateway(settings) -> PaymentGateway:
    settings.validate_stripe()
    return StripeGateway(settings.stripe_secret_key)
