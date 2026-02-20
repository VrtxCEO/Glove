import json
import os
import secrets
import shutil
import sys
import tempfile
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import load_settings
from .db import GloveDB
from .models import (
    AgentDecisionOut,
    AgentRequestIn,
    ApprovePinIn,
    ExtensionConfigIn,
    ExtensionInstallUrlIn,
    ExtensionTestIn,
    MessageReplyIn,
    RiskKeywordsConfigIn,
    SetupPinIn,
)
from .notifier import Notifier
from .policy import PolicyDecision, PolicyEngine
from .security import hash_pin, new_request_id, verify_pin
from .signature import SignatureError, load_trust_store, verify_extension_zip_signature


settings = load_settings()
db = GloveDB(settings.db_path)
policy_engine = PolicyEngine(settings.policy_path)
notifier = Notifier(settings)

app = FastAPI(title="Glove Safety Shell", version="0.1.0")
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    static_dir = Path(sys._MEIPASS) / "glove" / "static"  # type: ignore[attr-defined]
else:
    static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _read_or_create_key(name: str) -> str:
    existing = db.get_setting(name)
    if existing:
        return existing
    generated = secrets.token_urlsafe(24)
    db.set_setting(name, generated)
    return generated


AGENT_KEY = os.getenv("GLOVE_AGENT_KEY", "").strip() or _read_or_create_key("agent_key")
ADMIN_KEY = os.getenv("GLOVE_ADMIN_KEY", "").strip() or _read_or_create_key("admin_key")


def _require_agent(x_glove_agent_key: Optional[str] = Header(default=None)) -> None:
    if not x_glove_agent_key or x_glove_agent_key != AGENT_KEY:
        raise HTTPException(status_code=401, detail="invalid_agent_key")


def _require_admin(x_glove_admin_key: Optional[str] = Header(default=None)) -> None:
    if not x_glove_admin_key or x_glove_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="invalid_admin_key")


def _has_pin() -> bool:
    return bool(db.get_setting("pin_salt") and db.get_setting("pin_hash"))


def _get_enabled_extensions() -> list[str]:
    raw = db.get_setting("clawhub_enabled_extensions")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [x.strip() for x in settings.clawhub_extensions.split(",") if x.strip()]


def _approval_ui_url(request_id: str) -> str:
    base = settings.public_url.rstrip("/")
    return f"{base}/?request_id={request_id}"


def _approval_ui_url_from_metadata(request_id: str, metadata: Dict[str, Any]) -> str:
    raw = str(metadata.get("ui_base_url", "")).strip()
    if not raw:
        return _approval_ui_url(request_id)
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _approval_ui_url(request_id)
    base = raw.rstrip("/")
    return f"{base}/?request_id={request_id}"


def _normalize_keywords(keywords: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for raw in keywords:
        kw = str(raw).strip().lower()
        if not kw or len(kw) > 64:
            continue
        if kw in seen:
            continue
        seen.add(kw)
        out.append(kw)
    return out


def _get_risk_keywords() -> list[str]:
    raw = db.get_setting("risk_keywords")
    if not raw:
        return []
    return _normalize_keywords([x for x in raw.split(",") if x.strip()])


def _install_extension_from_zip_bytes(
    zip_bytes: bytes,
    replace_existing: bool,
    key_id: Optional[str],
    signature_b64: Optional[str],
) -> str:
    if len(zip_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="zip_too_large")

    if settings.require_extension_signatures:
        if not key_id or not signature_b64:
            raise HTTPException(status_code=400, detail="signature_required")
        try:
            trust_store = load_trust_store(settings.clawhub_trust_store_path)
            verify_extension_zip_signature(zip_bytes, trust_store, key_id, signature_b64)
        except SignatureError as exc:
            raise HTTPException(status_code=400, detail=f"signature_invalid: {exc}")

    ext_root = Path(settings.clawhub_extensions_dir).resolve()
    ext_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="glove-ext-") as tmp:
        tmp_path = Path(tmp).resolve()
        zip_path = tmp_path / "extension.zip"
        zip_path.write_bytes(zip_bytes)

        with zipfile.ZipFile(str(zip_path), "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                member_path = (tmp_path / member.filename).resolve()
                if not str(member_path).startswith(str(tmp_path)):
                    raise HTTPException(status_code=400, detail="invalid_zip_paths")
            zf.extractall(path=str(tmp_path))

        manifests = list(tmp_path.rglob("glove-extension.json"))
        if len(manifests) != 1:
            raise HTTPException(status_code=400, detail="zip_must_contain_one_extension_manifest")

        manifest_path = manifests[0]
        extension_dir = manifest_path.parent
        extension_id = extension_dir.name.strip()
        if not extension_id:
            raise HTTPException(status_code=400, detail="invalid_extension_id")
        if any(c for c in extension_id if c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."):
            raise HTTPException(status_code=400, detail="invalid_extension_id_chars")

        target_dir = (ext_root / extension_id).resolve()
        if target_dir.exists():
            if not replace_existing:
                raise HTTPException(status_code=409, detail="extension_exists")
            shutil.rmtree(target_dir)

        shutil.copytree(str(extension_dir), str(target_dir))
        return extension_id


@app.get("/")
def web_ui():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/api/v1/admin/bootstrap", dependencies=[Depends(_require_admin)])
def admin_bootstrap() -> Dict[str, Any]:
    return {"pin_configured": _has_pin()}


@app.post("/api/v1/admin/setup-pin", dependencies=[Depends(_require_admin)])
def setup_pin(payload: SetupPinIn) -> Dict[str, Any]:
    salt_b64, digest_b64, iterations = hash_pin(payload.pin)
    db.set_setting("pin_salt", salt_b64)
    db.set_setting("pin_hash", digest_b64)
    db.set_setting("pin_iterations", str(iterations))
    db.append_audit("pin_setup", "success", {"source": "admin"})
    return {"status": "ok"}


@app.get("/api/v1/admin/requests/pending", dependencies=[Depends(_require_admin)])
def list_pending() -> Dict[str, Any]:
    return {"items": db.list_pending_requests()}


@app.get("/api/v1/admin/audit/recent", dependencies=[Depends(_require_admin)])
def recent_audit() -> Dict[str, Any]:
    return {"items": db.recent_audit(100)}


@app.get("/api/v1/admin/risk-keywords", dependencies=[Depends(_require_admin)])
def get_risk_keywords() -> Dict[str, Any]:
    return {"keywords": _get_risk_keywords()}


@app.post("/api/v1/admin/risk-keywords/config", dependencies=[Depends(_require_admin)])
def set_risk_keywords(payload: RiskKeywordsConfigIn) -> Dict[str, Any]:
    keywords = _normalize_keywords(payload.keywords)
    db.set_setting("risk_keywords", ",".join(keywords))
    db.append_audit("risk_keywords_config", "success", {"count": len(keywords), "keywords": keywords})
    return {"status": "ok", "keywords": keywords}


@app.get("/api/v1/admin/extensions", dependencies=[Depends(_require_admin)])
def list_extensions() -> Dict[str, Any]:
    installed = notifier.discover_clawhub_extensions()
    enabled = _get_enabled_extensions()
    return {
        "extensions_dir": settings.clawhub_extensions_dir,
        "installed": installed,
        "enabled": [x for x in enabled if x in installed],
    }


@app.post("/api/v1/admin/extensions/config", dependencies=[Depends(_require_admin)])
def set_extensions(payload: ExtensionConfigIn) -> Dict[str, Any]:
    installed = set(notifier.discover_clawhub_extensions())
    enabled = [x for x in payload.enabled_ids if x in installed]
    db.set_setting("clawhub_enabled_extensions", ",".join(enabled))
    db.append_audit("extensions_config", "success", {"enabled": enabled})
    return {"status": "ok", "enabled": enabled}


@app.post("/api/v1/admin/extensions/test", dependencies=[Depends(_require_admin)])
def test_extension(payload: ExtensionTestIn) -> Dict[str, Any]:
    installed = notifier.discover_clawhub_extensions()
    if payload.extension_id not in installed:
        raise HTTPException(status_code=404, detail="extension_not_found")
    try:
        notifier.test_clawhub_extension(payload.extension_id)
        db.append_audit("extensions_test", "success", {"extension_id": payload.extension_id})
        return {"status": "ok", "extension_id": payload.extension_id}
    except Exception as exc:
        db.append_audit(
            "extensions_test",
            "failed",
            {"extension_id": payload.extension_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"extension_test_failed: {exc}")


@app.post("/api/v1/admin/extensions/install-url", dependencies=[Depends(_require_admin)])
def install_extension_url(payload: ExtensionInstallUrlIn) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(payload.url, timeout=20) as resp:
            zip_bytes = resp.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"download_failed: {exc}")

    extension_id = _install_extension_from_zip_bytes(
        zip_bytes,
        payload.replace_existing,
        payload.key_id,
        payload.signature_b64,
    )
    db.append_audit(
        "extensions_install",
        "success",
        {"source": "url", "url": payload.url, "extension_id": extension_id, "key_id": payload.key_id},
    )
    return {"status": "ok", "extension_id": extension_id}


@app.post("/api/v1/admin/extensions/install-upload", dependencies=[Depends(_require_admin)])
async def install_extension_upload(
    file: UploadFile = File(...),
    key_id: str = Form(...),
    signature_b64: str = Form(...),
    replace_existing: bool = Form(False),
) -> Dict[str, Any]:
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="file_must_be_zip")
    zip_bytes = await file.read()
    extension_id = _install_extension_from_zip_bytes(zip_bytes, replace_existing, key_id, signature_b64)
    db.append_audit(
        "extensions_install",
        "success",
        {"source": "upload", "filename": file.filename, "extension_id": extension_id, "key_id": key_id},
    )
    return {"status": "ok", "extension_id": extension_id}


@app.post("/api/v1/admin/approve-pin", dependencies=[Depends(_require_admin)])
def approve_pin(payload: ApprovePinIn) -> Dict[str, Any]:
    request = db.get_request(payload.request_id)
    if not request:
        raise HTTPException(status_code=404, detail="request_not_found")
    if request["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"request_{request['status']}")
    if datetime.fromisoformat(request["expires_at"]) < datetime.now(timezone.utc):
        db.set_request_status(payload.request_id, "expired")
        db.append_audit("approve_pin", "expired", {"reason": "request_expired"}, payload.request_id)
        raise HTTPException(status_code=409, detail="request_expired")

    salt_b64 = db.get_setting("pin_salt")
    digest_b64 = db.get_setting("pin_hash")
    iterations = int(db.get_setting("pin_iterations") or "210000")
    if not (salt_b64 and digest_b64):
        raise HTTPException(status_code=409, detail="pin_not_configured")

    if not verify_pin(payload.pin, salt_b64, digest_b64, iterations):
        attempts = db.increment_attempts(payload.request_id)
        outcome = "failed"
        if attempts >= settings.max_pin_attempts:
            db.set_request_status(payload.request_id, "denied")
            outcome = "locked"
        db.append_audit(
            "approve_pin",
            outcome,
            {"attempts": attempts, "max_attempts": settings.max_pin_attempts},
            payload.request_id,
            request["action"],
            request["target"],
        )
        raise HTTPException(status_code=401, detail="invalid_pin")

    db.set_request_status(payload.request_id, "approved")
    approval_token = secrets.token_urlsafe(24)
    db.append_audit(
        "approve_pin",
        "approved",
        {"approval_token_tail": approval_token[-8:]},
        payload.request_id,
        request["action"],
        request["target"],
    )
    return {"status": "approved", "approval_token": approval_token, "request_id": payload.request_id}


@app.post("/api/v1/admin/message-reply", dependencies=[Depends(_require_admin)])
def approve_from_message(payload: MessageReplyIn) -> Dict[str, Any]:
    # Expected format: PIN <request_id> <pin>
    parts = payload.body.strip().split()
    if len(parts) != 3 or parts[0].upper() != "PIN":
        raise HTTPException(status_code=400, detail="invalid_format")
    request_id = parts[1].strip()
    pin = parts[2].strip()
    return approve_pin(ApprovePinIn(request_id=request_id, pin=pin))


@app.post("/api/v1/inbound/reply")
def inbound_reply(
    token: str,
    body: Optional[str] = Form(default=None),
    Body: Optional[str] = Form(default=None),
) -> Dict[str, Any]:
    if not settings.inbound_token or token != settings.inbound_token:
        raise HTTPException(status_code=401, detail="invalid_inbound_token")
    raw = (body or Body or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="missing_message_body")
    return approve_from_message(  # reuse parser/approval flow
        MessageReplyIn(body=raw),
    )


@app.post("/api/v1/agent/request", response_model=AgentDecisionOut, dependencies=[Depends(_require_agent)])
def agent_request(payload: AgentRequestIn) -> AgentDecisionOut:
    keyword_match = None
    keywords = _get_risk_keywords()
    if keywords:
        haystack = (
            f"{payload.action}\n{payload.target}\n"
            f"{json.dumps(payload.metadata, sort_keys=True, ensure_ascii=False)}"
        ).lower()
        for kw in keywords:
            if kw in haystack:
                keyword_match = kw
                break

    if keyword_match:
        decision = PolicyDecision(
            decision="require_pin",
            risk="high",
            reason=f"Risk keyword matched: '{keyword_match}'",
            policy_id="policy-risk-keyword",
        )
    else:
        decision = policy_engine.evaluate(payload.action, payload.target, payload.metadata)

    if decision.decision == "deny":
        db.append_audit(
            "agent_request",
            "deny",
            {"reason": decision.reason, "policy_id": decision.policy_id},
            None,
            payload.action,
            payload.target,
        )
        return AgentDecisionOut(
            decision="deny",
            reason=decision.reason,
            policy_id=decision.policy_id,
            risk=decision.risk,
        )

    if decision.decision == "allow":
        db.append_audit(
            "agent_request",
            "allow",
            {"reason": decision.reason, "policy_id": decision.policy_id},
            None,
            payload.action,
            payload.target,
        )
        return AgentDecisionOut(
            decision="allow",
            reason=decision.reason,
            policy_id=decision.policy_id,
            risk=decision.risk,
        )

    request_id = new_request_id()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=settings.request_ttl_seconds)).isoformat()
    db.create_request(
        request_id=request_id,
        action=payload.action,
        target=payload.target,
        metadata=payload.metadata,
        risk=decision.risk,
        reason=decision.reason,
        policy_id=decision.policy_id,
        expires_at=expires_at,
    )
    db.append_audit(
        "agent_request",
        "require_pin",
        {"reason": decision.reason, "policy_id": decision.policy_id},
        request_id,
        payload.action,
        payload.target,
    )

    ui_link = _approval_ui_url_from_metadata(request_id, payload.metadata)
    msg = (
        f"Glove approval needed.\n"
        f"Request: {request_id}\n"
        f"Action: {payload.action}\n"
        f"Target: {payload.target}\n"
        f"Approve in Glove UI: {ui_link}\n"
    )

    try:
        notifier.send(
            "Glove PIN Required",
            msg,
            {"request_id": request_id},
            options={"clawhub_extensions": _get_enabled_extensions()},
        )
    except Exception as exc:
        db.append_audit(
            "notify",
            "failed",
            {"error": str(exc)},
            request_id,
            payload.action,
            payload.target,
        )

    return AgentDecisionOut(
        decision="require_pin",
        reason=decision.reason,
        policy_id=decision.policy_id,
        risk=decision.risk,
        request_id=request_id,
        expires_at=expires_at,
        ui_url=ui_link,
    )


@app.get("/api/v1/agent/request-status", dependencies=[Depends(_require_agent)])
def agent_request_status(request_id: str) -> Dict[str, Any]:
    request = db.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="request_not_found")

    status = request["status"]
    if status == "pending" and datetime.fromisoformat(request["expires_at"]) < datetime.now(timezone.utc):
        db.set_request_status(request_id, "expired")
        status = "expired"

    return {
        "request_id": request_id,
        "status": status,
        "action": request["action"],
        "target": request["target"],
        "expires_at": request["expires_at"],
        "approved_at": request.get("approved_at"),
    }


@app.get("/api/v1/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "pin_configured": _has_pin(),
        "notifier": settings.notifier_provider,
        "agent_key_tail": AGENT_KEY[-8:],
        "admin_key_tail": ADMIN_KEY[-8:],
    }


@app.on_event("startup")
def startup_log() -> None:
    # Intentionally prints only tails so full keys are not leaked by default.
    print(
        json.dumps(
            {
                "event": "glove_startup",
                "admin_key_tail": ADMIN_KEY[-8:],
                "agent_key_tail": AGENT_KEY[-8:],
                "pin_configured": _has_pin(),
            }
        )
    )
