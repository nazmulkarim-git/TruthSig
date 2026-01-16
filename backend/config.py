import os
from typing import Iterable, List


def env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}

def env_list(name: str, default: Iterable[str] | None = None) -> List[str]:
    value = os.getenv(name, "")
    if not value:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


TRUTHSIG_ENV = os.getenv("TRUTHSIG_ENV", "development")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "168"))
ADMIN_API_KEY = os.getenv("TRUTHSIG_ADMIN_API_KEY", "")

PAYWALL_ENABLED = env_bool("TRUTHSIG_PAYWALL_ENABLED", False)
PRICE_USD = int(os.getenv("TRUTHSIG_PRICE_USD", "15"))
MAX_MB = int(os.getenv("TRUTHSIG_MAX_MB", "50"))
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")

CORS_ORIGINS = env_list(
    "CORS_ORIGINS",
    default=[
        "https://truthsig-web.onrender.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
)
TRUSTED_HOSTS = env_list("TRUSTED_HOSTS", default=["*"])


def validate_production_settings() -> None:
    if TRUTHSIG_ENV.lower() != "production":
        return

    errors = []
    if not ADMIN_API_KEY:
        errors.append("TRUTHSIG_ADMIN_API_KEY is required in production.")
    if JWT_SECRET == "dev-secret-change-me":
        errors.append("JWT_SECRET must be set in production.")
    if not CORS_ORIGINS or "*" in CORS_ORIGINS:
        errors.append("CORS_ORIGINS must be explicit in production.")
    if errors:
        raise RuntimeError(" ".join(errors))