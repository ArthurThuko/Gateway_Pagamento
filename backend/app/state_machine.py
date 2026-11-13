from dataclasses import dataclass
from enum import Enum


class OrderStatus(str, Enum):
    PENDENTE = "pendente"
    RECUSADO = "recusado"
    PAGO = "pago"
    ENVIADO = "enviado"
    ESTORNADO = "estornado"


class OrderEvent(str, Enum):
    PAGAMENTO_CONFIRMADO = "pagamento_confirmado"   # webhook payment_intent.succeeded
    PAGAMENTO_RECUSADO = "pagamento_recusado"       # webhook payment_intent.payment_failed
    PEDIDO_ENVIADO = "pedido_enviado"               # ação interna (logística)
    PAGAMENTO_ESTORNADO = "pagamento_estornado"     # webhook charge.refunded (estorno total)


S, E = OrderStatus, OrderEvent

TRANSITIONS: dict[tuple[OrderStatus, OrderEvent], OrderStatus] = {
    (S.PENDENTE, E.PAGAMENTO_CONFIRMADO): S.PAGO,
    (S.RECUSADO, E.PAGAMENTO_CONFIRMADO): S.PAGO,       # o cliente tentou de novo e passou
    (S.PENDENTE, E.PAGAMENTO_RECUSADO): S.RECUSADO,
    (S.PAGO, E.PEDIDO_ENVIADO): S.ENVIADO,
    # Estorno implica que houve pagamento. Se o "estornado" chegar antes do "pago"
    # (fora de ordem), pulamos direto para ESTORNADO; o "pago" atrasado será ignorado.
    (S.PENDENTE, E.PAGAMENTO_ESTORNADO): S.ESTORNADO,
    (S.RECUSADO, E.PAGAMENTO_ESTORNADO): S.ESTORNADO,
    (S.PAGO, E.PAGAMENTO_ESTORNADO): S.ESTORNADO,
    (S.ENVIADO, E.PAGAMENTO_ESTORNADO): S.ESTORNADO,
}

# Usado só para documentar/testar a invariante "o estado só avança".
RANK = {S.PENDENTE: 0, S.RECUSADO: 1, S.PAGO: 2, S.ENVIADO: 3, S.ESTORNADO: 4}


@dataclass(frozen=True)
class Decision:
    applied: bool
    new_status: OrderStatus
    reason: str


def decide(current: OrderStatus, event: OrderEvent) -> Decision:
    target = TRANSITIONS.get((current, event))
    if target is not None:
        return Decision(True, target, f"{current.value} -> {target.value}")
    return Decision(False, current, f"evento '{event.value}' ignorado: o pedido já está '{current.value}'")
