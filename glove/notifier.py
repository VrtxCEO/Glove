import base64
import json
import smtplib
import subprocess
from pathlib import Path
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Dict, List, Optional

from .config import Settings


class Notifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(
        self,
        subject: str,
        message: str,
        payload: Dict[str, str],
        options: Optional[Dict[str, object]] = None,
    ) -> None:
        providers = self._providers()
        errors: List[str] = []
        for provider in providers:
            try:
                if provider == "webhook":
                    self._send_webhook(subject, message, payload)
                elif provider == "smtp":
                    self._send_smtp(subject, message)
                elif provider == "twilio":
                    self._send_twilio(message)
                elif provider == "clawhub":
                    self._send_clawhub(subject, message, payload, options or {})
                else:
                    self._send_console(subject, message, payload)
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
        if errors and len(errors) == len(providers):
            raise RuntimeError("all notifier providers failed: " + "; ".join(errors))

    def _providers(self) -> List[str]:
        if self.settings.notifier_providers:
            providers = [p.strip().lower() for p in self.settings.notifier_providers.split(",") if p.strip()]
            return providers or ["console"]
        return [self.settings.notifier_provider or "console"]

    def _send_console(self, subject: str, message: str, payload: Dict[str, str]) -> None:
        print("[GLOVE][NOTIFY]", subject, message, payload)

    def _send_webhook(self, subject: str, message: str, payload: Dict[str, str]) -> None:
        if not self.settings.webhook_url:
            raise RuntimeError("GLOVE_WEBHOOK_URL is required for webhook notifier.")
        body = json.dumps({"subject": subject, "message": message, "payload": payload}).encode("utf-8")
        req = urllib.request.Request(
            self.settings.webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            return

    def _send_smtp(self, subject: str, message: str) -> None:
        if not all([self.settings.smtp_host, self.settings.smtp_from, self.settings.notify_to]):
            raise RuntimeError("SMTP notifier requires host/from/to settings.")
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.settings.smtp_from
        msg["To"] = self.settings.notify_to
        msg.set_content(message)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as client:
            if self.settings.smtp_use_tls:
                client.starttls()
            if self.settings.smtp_username:
                client.login(self.settings.smtp_username, self.settings.smtp_password)
            client.send_message(msg)

    def _send_twilio(self, message: str) -> None:
        required = [
            self.settings.twilio_account_sid,
            self.settings.twilio_auth_token,
            self.settings.twilio_from,
            self.settings.twilio_to,
        ]
        if not all(required):
            raise RuntimeError("Twilio notifier requires account sid/auth token/from/to.")

        sid = self.settings.twilio_account_sid
        token = self.settings.twilio_auth_token
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

        form = urllib.parse.urlencode(
            {"From": self.settings.twilio_from, "To": self.settings.twilio_to, "Body": message}
        ).encode("utf-8")
        auth = base64.b64encode(f"{sid}:{token}".encode("utf-8")).decode("ascii")

        req = urllib.request.Request(
            url,
            data=form,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            return

    def _send_clawhub(
        self,
        subject: str,
        message: str,
        payload: Dict[str, str],
        options: Dict[str, object],
    ) -> None:
        ext_dir = Path(self.settings.clawhub_extensions_dir).resolve()
        ext_ids = self._resolve_extension_ids(options)
        if not ext_ids:
            raise RuntimeError("GLOVE_CLAWHUB_EXTENSIONS is empty.")
        if not ext_dir.exists():
            raise RuntimeError(f"ClawHub extensions dir missing: {ext_dir}")

        envelope = {
            "event": "notify",
            "subject": subject,
            "message": message,
            "payload": payload,
        }
        failed = []
        for ext_id in ext_ids:
            try:
                self._invoke_clawhub_extension(ext_dir, ext_id, envelope)
            except Exception as exc:
                failed.append(f"{ext_id}: {exc}")
        if failed:
            raise RuntimeError("ClawHub extension failures: " + "; ".join(failed))

    def discover_clawhub_extensions(self) -> List[str]:
        ext_dir = Path(self.settings.clawhub_extensions_dir).resolve()
        if not ext_dir.exists():
            return []
        found: List[str] = []
        for child in ext_dir.iterdir():
            if not child.is_dir():
                continue
            manifest_path = child / "glove-extension.json"
            if manifest_path.exists():
                found.append(child.name)
        found.sort()
        return found

    def test_clawhub_extension(self, extension_id: str) -> None:
        ext_dir = Path(self.settings.clawhub_extensions_dir).resolve()
        envelope = {
            "event": "notify_test",
            "subject": "Glove Extension Test",
            "message": "Test from Glove admin UI",
            "payload": {"source": "admin_test"},
        }
        self._invoke_clawhub_extension(ext_dir, extension_id, envelope)

    def _resolve_extension_ids(self, options: Dict[str, object]) -> List[str]:
        override = options.get("clawhub_extensions")
        if isinstance(override, list):
            return [str(x).strip() for x in override if str(x).strip()]
        return [x.strip() for x in self.settings.clawhub_extensions.split(",") if x.strip()]

    def _invoke_clawhub_extension(self, ext_root: Path, ext_id: str, envelope: Dict[str, str]) -> None:
        manifest_path = ext_root / ext_id / "glove-extension.json"
        if not manifest_path.exists():
            raise RuntimeError(f"missing manifest {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        notify = manifest.get("notify", {})
        command = notify.get("command", "").strip()
        args = notify.get("args", [])
        if not command:
            raise RuntimeError("notify.command missing")
        if not isinstance(args, list):
            raise RuntimeError("notify.args must be array")

        proc = subprocess.run(
            [command] + [str(a) for a in args],
            input=json.dumps(envelope),
            text=True,
            capture_output=True,
            cwd=str(manifest_path.parent),
            timeout=max(1, self.settings.clawhub_timeout_seconds),
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"exit={proc.returncode} stderr={proc.stderr.strip()}")
