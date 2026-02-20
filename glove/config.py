import os
from dataclasses import dataclass


def _as_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    db_path: str
    policy_path: str
    request_ttl_seconds: int
    max_pin_attempts: int
    inbound_token: str
    notifier_provider: str
    notifier_providers: str
    public_url: str
    webhook_url: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    smtp_from: str
    notify_to: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from: str
    twilio_to: str
    clawhub_extensions_dir: str
    clawhub_extensions: str
    clawhub_timeout_seconds: int
    clawhub_trust_store_path: str
    require_extension_signatures: bool


def load_settings() -> Settings:
    return Settings(
        host=os.getenv("GLOVE_HOST", "0.0.0.0"),
        port=int(os.getenv("GLOVE_PORT", "8088")),
        db_path=os.getenv("GLOVE_DB_PATH", "./glove.db"),
        policy_path=os.getenv("GLOVE_POLICY_PATH", "./policy.json"),
        request_ttl_seconds=int(os.getenv("GLOVE_REQUEST_TTL_SECONDS", "300")),
        max_pin_attempts=int(os.getenv("GLOVE_MAX_PIN_ATTEMPTS", "5")),
        inbound_token=os.getenv("GLOVE_INBOUND_TOKEN", "").strip(),
        notifier_provider=os.getenv("GLOVE_NOTIFIER_PROVIDER", "console").strip().lower(),
        notifier_providers=os.getenv("GLOVE_NOTIFIER_PROVIDERS", "").strip().lower(),
        public_url=os.getenv("GLOVE_PUBLIC_URL", "http://127.0.0.1:8088").strip(),
        webhook_url=os.getenv("GLOVE_WEBHOOK_URL", "").strip(),
        smtp_host=os.getenv("GLOVE_SMTP_HOST", "").strip(),
        smtp_port=int(os.getenv("GLOVE_SMTP_PORT", "587")),
        smtp_username=os.getenv("GLOVE_SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("GLOVE_SMTP_PASSWORD", "").strip(),
        smtp_use_tls=_as_bool(os.getenv("GLOVE_SMTP_USE_TLS"), True),
        smtp_from=os.getenv("GLOVE_SMTP_FROM", "").strip(),
        notify_to=os.getenv("GLOVE_NOTIFY_TO", "").strip(),
        twilio_account_sid=os.getenv("GLOVE_TWILIO_ACCOUNT_SID", "").strip(),
        twilio_auth_token=os.getenv("GLOVE_TWILIO_AUTH_TOKEN", "").strip(),
        twilio_from=os.getenv("GLOVE_TWILIO_FROM", "").strip(),
        twilio_to=os.getenv("GLOVE_TWILIO_TO", "").strip(),
        clawhub_extensions_dir=os.getenv("GLOVE_CLAWHUB_EXTENSIONS_DIR", "./extensions").strip(),
        clawhub_extensions=os.getenv("GLOVE_CLAWHUB_EXTENSIONS", "").strip(),
        clawhub_timeout_seconds=int(os.getenv("GLOVE_CLAWHUB_TIMEOUT_SECONDS", "10")),
        clawhub_trust_store_path=os.getenv("GLOVE_CLAWHUB_TRUST_STORE_PATH", "./trusted_publishers.json").strip(),
        require_extension_signatures=_as_bool(os.getenv("GLOVE_REQUIRE_EXTENSION_SIGNATURES"), True),
    )
