import hashlib
import hmac
import time


class SignatureError(Exception):
    pass


def _hmac_hex(secret: str, timestamp: int, payload: bytes) -> str:
    signed = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def sign_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    return f"t={ts},v1={_hmac_hex(secret, ts, payload)}"


def verify_signature(payload: bytes, header: str | None, secret: str,
                     tolerance_seconds: int = 300, now: float | None = None) -> None:
    if not header:
        raise SignatureError("cabeçalho Stripe-Signature ausente")

    campos = [p.split("=", 1) for p in header.split(",") if "=" in p]
    timestamps = [v.strip() for k, v in campos if k.strip() == "t"]
    candidatas = [v.strip() for k, v in campos if k.strip() == "v1"]
    if not timestamps or not candidatas:
        raise SignatureError("cabeçalho em formato inválido")
    try:
        ts = int(timestamps[0])
    except ValueError:
        raise SignatureError("timestamp inválido") from None

    esperada = _hmac_hex(secret, ts, payload)
    # compare_digest: comparação em tempo constante (evita vazar a assinatura por timing).
    if not any(hmac.compare_digest(esperada.encode(), c.encode()) for c in candidatas):
        raise SignatureError("assinatura não confere")

    # Anti-replay: um webhook autêntico, mas capturado há muito tempo, não vale.
    agora = time.time() if now is None else now
    if abs(agora - ts) > tolerance_seconds:
        raise SignatureError("timestamp fora da tolerância (possível replay)")
