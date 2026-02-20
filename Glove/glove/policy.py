import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class PolicyDecision:
    decision: str
    risk: str
    reason: str
    policy_id: str


class PolicyEngine:
    def __init__(self, policy_path: str):
        with open(policy_path, "r", encoding="utf-8") as f:
            self._policy = json.load(f)

    def evaluate(self, action: str, target: str, metadata: Dict[str, Any]) -> PolicyDecision:
        blocked_targets = self._policy.get("blocked_targets", [])
        for blocked in blocked_targets:
            if blocked and blocked.lower() in target.lower():
                return PolicyDecision(
                    decision="deny",
                    risk="high",
                    reason=f"Target is blocked by policy: {blocked}",
                    policy_id="policy-blocked-target",
                )

        rules = self._policy.get("rules", [])
        rule = self._find_best_rule(action, rules)
        default_risk = self._policy.get("default_risk", "medium")
        if not rule:
            return self._risk_to_decision(default_risk, "default-policy", "Default policy applied.")

        if rule.get("decision") == "deny":
            return PolicyDecision(
                decision="deny",
                risk=rule.get("risk", "high"),
                reason=rule.get("reason", "Denied by policy rule."),
                policy_id=rule.get("id", "policy-unnamed"),
            )

        risk = rule.get("risk", default_risk)
        reason = rule.get("reason", "Rule-based policy applied.")
        return self._risk_to_decision(risk, rule.get("id", "policy-unnamed"), reason)

    @staticmethod
    def _find_best_rule(action: str, rules: list) -> Optional[Dict[str, Any]]:
        matches = []
        for rule in rules:
            prefix = rule.get("action_prefix", "")
            if prefix and action.startswith(prefix):
                matches.append((len(prefix), rule))
        if not matches:
            return None
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1]

    @staticmethod
    def _risk_to_decision(risk: str, policy_id: str, reason: str) -> PolicyDecision:
        normalized = risk.lower()
        if normalized == "high":
            return PolicyDecision(decision="require_pin", risk="high", reason=reason, policy_id=policy_id)
        return PolicyDecision(decision="allow", risk=normalized, reason=reason, policy_id=policy_id)
