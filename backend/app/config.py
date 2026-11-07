import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        chave, valor = line.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    stripe_secret_key: str
    stripe_publishable_key: str
    webhook_secret: str
    webhook_tolerance_seconds: int
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    cors_origins: list

    def validate_stripe(self) -> None:
        problemas = []
        if not self.stripe_secret_key.startswith("sk_test_"):
            problemas.append("STRIPE_SECRET_KEY deve começar com sk_test_")
        if not self.stripe_publishable_key.startswith("pk_test_"):
            problemas.append("STRIPE_PUBLISHABLE_KEY deve começar com pk_test_")
        if not self.webhook_secret.startswith("whsec_"):
            problemas.append("STRIPE_WEBHOOK_SECRET deve começar com whsec_ (veja `stripe listen`)")
        if problemas:
            raise RuntimeError("Configuração do Stripe inválida:\n  - " + "\n  - ".join(problemas))


def load_settings() -> Settings:
    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    env = os.environ.get
    return Settings(
        stripe_secret_key=env("STRIPE_SECRET_KEY", ""),
        stripe_publishable_key=env("STRIPE_PUBLISHABLE_KEY", ""),
        webhook_secret=env("STRIPE_WEBHOOK_SECRET", ""),
        webhook_tolerance_seconds=int(env("WEBHOOK_TOLERANCE_SECONDS", "300")),
        mysql_host=env("MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(env("MYSQL_PORT", "3306")),
        mysql_user=env("MYSQL_USER", "root"),
        mysql_password=env("MYSQL_PASSWORD", ""),
        mysql_database=env("MYSQL_DATABASE", "loja"),
        cors_origins=[o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    )
