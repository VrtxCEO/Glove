import base64
import hashlib
import hmac
import secrets
from typing import Tuple


PBKDF2_ITERATIONS = 210_000


def hash_pin(pin: str) -> Tuple[str, str, int]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return (
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
        PBKDF2_ITERATIONS,
    )


def verify_pin(pin: str, salt_b64: str, digest_b64: str, iterations: int) -> bool:
    salt = base64.b64decode(salt_b64.encode("ascii"))
    expected = base64.b64decode(digest_b64.encode("ascii"))
    actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def new_request_id() -> str:
    return secrets.token_urlsafe(18)
