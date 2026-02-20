import base64
import hashlib
import json
from pathlib import Path

from nacl.signing import VerifyKey


class SignatureError(Exception):
    pass


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_trust_store(path: str) -> dict:
    p = Path(path).resolve()
    if not p.exists():
        return {"publishers": {}}
    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise SignatureError("invalid_trust_store_format")
    pubs = payload.get("publishers", {})
    if not isinstance(pubs, dict):
        raise SignatureError("invalid_publishers_format")
    return payload


def verify_extension_zip_signature(
    zip_bytes: bytes,
    trust_store: dict,
    key_id: str,
    signature_b64: str,
) -> None:
    publishers = trust_store.get("publishers", {})
    public_key_b64 = publishers.get(key_id)
    if not public_key_b64:
        raise SignatureError("unknown_publisher_key_id")

    try:
        pubkey = base64.b64decode(public_key_b64.encode("ascii"))
    except Exception as exc:
        raise SignatureError(f"invalid_trust_store_pubkey: {exc}")
    try:
        signature = base64.b64decode(signature_b64.encode("ascii"))
    except Exception as exc:
        raise SignatureError(f"invalid_signature_b64: {exc}")

    digest = sha256_hex(zip_bytes).encode("ascii")
    try:
        VerifyKey(pubkey).verify(digest, signature)
    except Exception as exc:
        raise SignatureError(f"signature_verification_failed: {exc}")
