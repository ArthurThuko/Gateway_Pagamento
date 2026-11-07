import json

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import services
from .config import Settings, load_settings
from .db import connect, init_db
from .gateway import PaymentGateway, build_gateway
from .signature import SignatureError, verify_signature


class ItemIn(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=99)


class OrderIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1)


def create_app(settings: Settings | None = None, gateway: PaymentGateway | None = None) -> FastAPI:
    settings = settings or load_settings()
    gateway = gateway or build_gateway(settings)
    init_db(settings)

    app = FastAPI(title="Loja com Stripe (modo de teste), MySQL e webhooks")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["Idempotent-Replayed"])

    def get_conn():
        conn = connect(settings)
        try:
            yield conn
        finally:
            conn.close()

    @app.exception_handler(services.DomainError)
    async def domain_error(_: Request, exc: services.DomainError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/config")
    def config():
        return {"publishable_key": settings.stripe_publishable_key}

    @app.get("/products")
    def products(conn=Depends(get_conn)):
        return list(conn.execute("SELECT id, name, price_cents FROM products ORDER BY name").fetchall())

    @app.post("/orders", status_code=201)
    def create_order(body: OrderIn, conn=Depends(get_conn)):
        return services.create_order(conn, [i.model_dump() for i in body.items])

    @app.get("/orders")
    def list_orders(conn=Depends(get_conn)):
        return services.list_orders(conn)

    @app.get("/orders/{order_id}")
    def get_order(order_id: str, conn=Depends(get_conn)):
        return services.get_order(conn, order_id)

    @app.post("/orders/{order_id}/pay")
    def pay(order_id: str, response: Response,
            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
            conn=Depends(get_conn)):
        if not idempotency_key or len(idempotency_key) > 200:
            raise HTTPException(status_code=400, detail="O header Idempotency-Key é obrigatório (até 200 caracteres).")
        resultado = services.pay_order(conn, gateway, order_id, idempotency_key)
        response.headers["Idempotent-Replayed"] = "true" if resultado.replayed else "false"
        return resultado.body

    @app.post("/orders/{order_id}/ship")
    def ship(order_id: str, conn=Depends(get_conn)):
        return services.ship_order(conn, order_id)

    def deliver(payload: bytes, signature_header: str | None) -> tuple[int, dict]:
        try:
            verify_signature(payload, signature_header, settings.webhook_secret, settings.webhook_tolerance_seconds)
        except SignatureError as exc:
            return 400, {"outcome": "rejected", "detail": f"Assinatura rejeitada: {exc}"}
        try:
            event = json.loads(payload)
        except ValueError:
            return 400, {"outcome": "rejected", "detail": "Corpo não é JSON válido."}
        conn = connect(settings)
        try:
            return 200, services.process_webhook(conn, event).as_dict()
        except services.MalformedEvent as exc:
            return 400, {"outcome": "rejected", "detail": exc.message}
        finally:
            conn.close()

    @app.post("/webhooks/stripe")
    async def stripe_webhook(request: Request):
        payload = await request.body()
        status, corpo = await run_in_threadpool(deliver, payload, request.headers.get("stripe-signature"))
        return JSONResponse(status_code=status, content=corpo)

    return app
