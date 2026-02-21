from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


class AgentRequestIn(BaseModel):
    action: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=500)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentDecisionOut(BaseModel):
    decision: Literal["allow", "deny", "require_pin"]
    reason: str
    policy_id: str
    risk: str
    request_id: str | None = None
    expires_at: str | None = None
    ui_url: str | None = None


class ApprovePinIn(BaseModel):
    request_id: str
    pin: str = Field(min_length=4, max_length=32)


class DenyRequestIn(BaseModel):
    request_id: str
    reason: str = Field(default="declined_by_user", min_length=1, max_length=200)


class SetupPinIn(BaseModel):
    pin: str = Field(min_length=4, max_length=32)


class MessageReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=300)


class ExtensionConfigIn(BaseModel):
    enabled_ids: list[str] = Field(default_factory=list)


class ExtensionTestIn(BaseModel):
    extension_id: str = Field(min_length=1, max_length=128)


class ExtensionInstallUrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    key_id: str = Field(min_length=1, max_length=128)
    signature_b64: str = Field(min_length=32, max_length=5000)
    replace_existing: bool = False


class RiskKeywordsConfigIn(BaseModel):
    keywords: list[str] = Field(default_factory=list)
