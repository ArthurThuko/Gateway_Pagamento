import json
import time
import uuid
from dataclasses import dataclass

from .db import is_duplicate, now_iso, transaction
from .gateway import PaymentGateway
from .state_machine import OrderEvent, OrderStatus, decide

PROCESSING_TIMEOUT_SECONDS = 60


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404


class InvalidOrder(DomainError):
    status_code = 422


class NotPayable(DomainError):
    status_code = 409


class InvalidTransition(DomainError):
    status_code = 409


class IdempotencyConflict(DomainError):
    status_code = 422


class RequestInProgress(DomainError):
    status_code = 409


class GatewayUnavailable(DomainError):
    status_code = 502


class MalformedEvent(DomainError):
    status_code = 400


def _apply_transition(conn, order_id, old: OrderStatus | None, new: OrderStatus, cause: str, event_id):
    agora = now_iso()
    conn.execute("UPDATE orders SET status = %s, updated_at = %s WHERE id = %s", (new.value, agora, order_id))
    conn.execute(
        "INSERT INTO order_history (order_id, from_status, to_status, cause, event_id, occurred_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (order_id, old.value if old else None, new.value, cause, event_id, agora),
    )


def create_order(conn, items: list[dict]) -> dict:
    if not items:
        raise InvalidOrder("O carrinho está vazio.")
    quantidades: dict[str, int] = {}
    for item in items:
        qtd = int(item["quantity"])
        if not 1 <= qtd <= 99:
            raise InvalidOrder("Quantidade deve estar entre 1 e 99.")
        quantidades[item["product_id"]] = quantidades.get(item["product_id"], 0) + qtd

    order_id = f"ord_{uuid.uuid4().hex[:16]}"
    with transaction(conn):
        total = 0
        linhas = []
        for pid, qtd in quantidades.items():
            produto = conn.execute("SELECT * FROM products WHERE id = %s", (pid,)).fetchone()
            if produto is None:
                raise InvalidOrder(f"Produto inexistente: {pid}")
            total += produto["price_cents"] * qtd
            linhas.append((order_id, pid, produto["name"], produto["price_cents"], qtd))
        agora = now_iso()
        conn.execute(
            "INSERT INTO orders (id, status, total_cents, currency, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'brl', %s, %s)",
            (order_id, OrderStatus.PENDENTE.value, total, agora, agora),
        )
        conn.executemany(
            "INSERT INTO order_items (order_id, product_id, name, unit_price_cents, quantity) "
            "VALUES (%s, %s, %s, %s, %s)", linhas)
        _apply_transition(conn, order_id, None, OrderStatus.PENDENTE, "pedido_criado", None)
    return get_order(conn, order_id)


def get_order(conn, order_id: str) -> dict:
    row = conn.execute("SELECT * FROM orders WHERE id = %s", (order_id,)).fetchone()
    if row is None:
        raise NotFound("Pedido não encontrado.")
    itens = conn.execute(
        "SELECT product_id, name, unit_price_cents, quantity FROM order_items WHERE order_id = %s ORDER BY id",
        (order_id,)).fetchall()
    historico = conn.execute(
        "SELECT from_status, to_status, cause, event_id, occurred_at FROM order_history "
        "WHERE order_id = %s ORDER BY id", (order_id,)).fetchall()
    return {  # client_secret nunca sai por aqui
        "id": row["id"], "status": row["status"], "total_cents": row["total_cents"], "currency": row["currency"],
        "payment_intent_id": row["payment_intent_id"], "created_at": row["created_at"],
        "updated_at": row["updated_at"], "items": list(itens), "history": list(historico),
    }


def list_orders(conn, limit: int = 20) -> list[dict]:
    ids = [r["id"] for r in conn.execute("SELECT id FROM orders ORDER BY created_at DESC LIMIT %s", (limit,))]
    return [get_order(conn, i) for i in ids]


def ship_order(conn, order_id: str) -> dict:
    with transaction(conn):
        row = conn.execute("SELECT * FROM orders WHERE id = %s FOR UPDATE", (order_id,)).fetchone()
        if row is None:
            raise NotFound("Pedido não encontrado.")
        atual = OrderStatus(row["status"])
        decisao = decide(atual, OrderEvent.PEDIDO_ENVIADO)
        if not decisao.applied:
            raise InvalidTransition(f"Só é possível enviar pedidos pagos (estado atual: {atual.value}).")
        _apply_transition(conn, order_id, atual, decisao.new_status, "envio_manual", None)
    return get_order(conn, order_id)


@dataclass(frozen=True)
class PayResult:
    body: dict
    replayed: bool


def _pay_body(order_id: str, payment_intent_id: str, client_secret: str) -> dict:
    return {"order_id": order_id, "payment_intent_id": payment_intent_id, "client_secret": client_secret}


def _guardar_chave(conn, chave, order_id, estado, resposta, agora):
    try:
        conn.execute(
            "INSERT INTO idempotency_keys (idem_key, order_id, state, response_json, created_epoch) "
            "VALUES (%s, %s, %s, %s, %s)", (chave, order_id, estado, resposta, agora))
    except Exception as exc:
        if is_duplicate(exc):   # outra requisição inseriu a mesma chave no mesmo instante
            raise IdempotencyConflict("Esta Idempotency-Key já está em uso por outra requisição.") from exc
        raise


def pay_order(conn, gateway: PaymentGateway, order_id: str, idempotency_key: str) -> PayResult:
    agora = int(time.time())
    with transaction(conn):
        pedido = conn.execute("SELECT * FROM orders WHERE id = %s FOR UPDATE", (order_id,)).fetchone()
        if pedido is None:
            raise NotFound("Pedido não encontrado.")

        salva = conn.execute("SELECT * FROM idempotency_keys WHERE idem_key = %s", (idempotency_key,)).fetchone()
        if salva is not None:
            if salva["order_id"] != order_id:
                raise IdempotencyConflict("Esta Idempotency-Key já foi usada em outro pedido.")
            if salva["state"] == "done":
                return PayResult(json.loads(salva["response_json"]), replayed=True)
            if agora - salva["created_epoch"] < PROCESSING_TIMEOUT_SECONDS:
                raise RequestInProgress("Pagamento em processamento; tente novamente com a mesma chave.")
            conn.execute("DELETE FROM idempotency_keys WHERE idem_key = %s", (idempotency_key,))  # abandonada

        estado = OrderStatus(pedido["status"])
        if estado not in (OrderStatus.PENDENTE, OrderStatus.RECUSADO):
            raise NotPayable(f"Pedido '{estado.value}' não aceita novo pagamento.")

        if pedido["payment_intent_id"]:
            corpo = _pay_body(order_id, pedido["payment_intent_id"], pedido["client_secret"])
            _guardar_chave(conn, idempotency_key, order_id, "done", json.dumps(corpo), agora)
            return PayResult(corpo, replayed=False)

        ocupado = conn.execute(
            "SELECT 1 AS x FROM idempotency_keys WHERE order_id = %s AND state = 'processing' AND created_epoch > %s",
            (order_id, agora - PROCESSING_TIMEOUT_SECONDS)).fetchone()
        if ocupado:
            raise RequestInProgress("Já existe um pagamento em andamento para este pedido.")
        _guardar_chave(conn, idempotency_key, order_id, "processing", None, agora)
        total, moeda = pedido["total_cents"], pedido["currency"]

    try:
        resultado = gateway.create_payment(order_id=order_id, amount_cents=total, currency=moeda,
                                           idempotency_key=f"pay-{order_id}")
    except Exception as exc:
        with transaction(conn):
            conn.execute("DELETE FROM idempotency_keys WHERE idem_key = %s", (idempotency_key,))
        raise GatewayUnavailable("O Stripe não respondeu; tente novamente com a mesma chave.") from exc

    corpo = _pay_body(order_id, resultado.id, resultado.client_secret)
    with transaction(conn):
        conn.execute("UPDATE orders SET payment_intent_id = %s, client_secret = %s, updated_at = %s WHERE id = %s",
                     (resultado.id, resultado.client_secret, now_iso(), order_id))
        conn.execute("UPDATE idempotency_keys SET state = 'done', response_json = %s WHERE idem_key = %s",
                     (json.dumps(corpo), idempotency_key))
    return PayResult(corpo, replayed=False)


@dataclass(frozen=True)
class WebhookResult:
    outcome: str
    order_id: str | None
    status: str | None
    detail: str

    def as_dict(self) -> dict:
        return {"outcome": self.outcome, "order_id": self.order_id, "status": self.status, "detail": self.detail}


def _validate(event) -> None:
    if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not isinstance(event.get("type"), str):
        raise MalformedEvent("Evento sem 'id' ou 'type'.")
    data = event.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("object"), dict):
        raise MalformedEvent("Evento sem 'data.object'.")
    if event.get("livemode") is True:
        raise MalformedEvent("Evento de produção (livemode=true) recusado: este projeto só aceita modo de teste.")


def _extract(event: dict):
    tipo, obj = event["type"], event["data"]["object"]
    meta = obj.get("metadata") or {}
    if tipo == "payment_intent.succeeded":
        return OrderEvent.PAGAMENTO_CONFIRMADO, meta.get("order_id"), obj.get("id")
    if tipo == "payment_intent.payment_failed":
        return OrderEvent.PAGAMENTO_RECUSADO, meta.get("order_id"), obj.get("id")
    if tipo == "charge.refunded" and obj.get("refunded") is True:   # só estorno TOTAL
        return OrderEvent.PAGAMENTO_ESTORNADO, meta.get("order_id"), obj.get("payment_intent")
    return None


def _find_order_for_update(conn, order_id, payment_intent_id):
    if order_id:
        row = conn.execute("SELECT * FROM orders WHERE id = %s FOR UPDATE", (order_id,)).fetchone()
        if row:
            return row
    if payment_intent_id:
        return conn.execute("SELECT * FROM orders WHERE payment_intent_id = %s FOR UPDATE",
                            (payment_intent_id,)).fetchone()
    return None


def _finalizar_evento(conn, event_id, order_id, outcome):
    conn.execute("UPDATE webhook_events SET order_id = %s, outcome = %s WHERE event_id = %s",
                 (order_id, outcome, event_id))


def process_webhook(conn, event: dict) -> WebhookResult:
    _validate(event)
    event_id, tipo = event["id"], event["type"]
    with transaction(conn):
        try:
            conn.execute(
                "INSERT INTO webhook_events (event_id, event_type, order_id, outcome, received_at) "
                "VALUES (%s, %s, NULL, 'processing', %s)", (event_id, tipo, now_iso()))
        except Exception as exc:
            if is_duplicate(exc):
                return WebhookResult("duplicate", None, None, "Evento já processado; nada a fazer.")
            raise

        extraido = _extract(event)
        if extraido is None:
            _finalizar_evento(conn, event_id, None, "unrelated")
            return WebhookResult("unrelated", None, None, f"Tipo '{tipo}' não altera pedidos.")

        evento, order_id, pi_id = extraido
        pedido = _find_order_for_update(conn, order_id, pi_id)
        if pedido is None:
            _finalizar_evento(conn, event_id, None, "unknown_order")
            return WebhookResult("unknown_order", None, None, "Nenhum pedido corresponde a este evento.")

        atual = OrderStatus(pedido["status"])
        decisao = decide(atual, evento)
        if decisao.applied:
            _apply_transition(conn, pedido["id"], atual, decisao.new_status, evento.value, event_id)
        outcome = "applied" if decisao.applied else "ignored"
        _finalizar_evento(conn, event_id, pedido["id"], outcome)
        return WebhookResult(outcome, pedido["id"], decisao.new_status.value, decisao.reason)
