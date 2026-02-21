const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const str = (v: unknown, fallback = "") => (typeof v === "string" ? v : fallback);
const num = (v: unknown, fallback: number) =>
  typeof v === "number" && Number.isFinite(v) ? v : fallback;
const bool = (v: unknown, fallback: boolean) => (typeof v === "boolean" ? v : fallback);
const arr = (v: unknown) =>
  Array.isArray(v) ? v.map((x) => String(x)).filter(Boolean) : [];

export default function register(api: any) {
  api.on(
    "before_tool_call",
    async (event: any, ctx: any) => {
      const cfg = (api.pluginConfig ?? {}) as Record<string, unknown>;
      if (!bool(cfg.enabled, true)) return;

      const toolName = str(event?.toolName, "unknown");
      const includeTools = arr(cfg.includeTools);
      const excludeTools = arr(cfg.excludeTools);

      if (includeTools.length > 0 && !includeTools.some((pattern) => toolName.includes(pattern))) {
        return;
      }
      if (excludeTools.some((pattern) => toolName.includes(pattern))) return;

      const baseUrl = str(cfg.baseUrl, "http://127.0.0.1:8088").replace(/\/+$/, "");
      const agentKey = str(cfg.agentKey, "").trim();
      if (!agentKey) {
        api.logger.warn("[glove-guard] Missing agentKey; skipping Glove check.");
        return;
      }

      const params = event?.params ?? {};
      const body = {
        action: `tool:${toolName}`,
        target: JSON.stringify(params).slice(0, 4000),
        metadata: {
          source: "openclaw-plugin:glove-guard",
          tool_name: toolName,
          session_key: str(ctx?.sessionKey, ""),
          agent_id: str(ctx?.agentId, "")
        }
      };

      let decision: any;
      try {
        const res = await fetch(`${baseUrl}/api/v1/agent/request`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Glove-Agent-Key": agentKey
          },
          body: JSON.stringify(body)
        });
        if (!res.ok) {
          const txt = await res.text();
          return { block: true, blockReason: `Glove error (${res.status}): ${txt.slice(0, 200)}` };
        }
        decision = await res.json();
      } catch (err: any) {
        return { block: true, blockReason: `Glove unreachable: ${String(err?.message ?? err)}` };
      }

      if (decision?.decision === "allow") return;
      if (decision?.decision === "deny") {
        return { block: true, blockReason: `Glove denied: ${str(decision?.reason, "policy")}` };
      }
      if (decision?.decision !== "require_pin") {
        return { block: true, blockReason: `Glove invalid decision: ${str(decision?.decision, "unknown")}` };
      }

      const requestId = str(decision?.request_id, "");
      const uiUrl = str(decision?.ui_url, `${baseUrl}/`);
      if (!requestId) {
        return { block: true, blockReason: `Glove missing request_id. Approve in Glove UI: ${uiUrl}` };
      }

      const intervalMs = num(cfg.pollIntervalMs, 1500);
      const timeoutMs = num(cfg.pollTimeoutMs, 300000);
      const deadline = Date.now() + timeoutMs;

      while (Date.now() < deadline) {
        await sleep(intervalMs);
        try {
          const statusRes = await fetch(
            `${baseUrl}/api/v1/agent/request-status?request_id=${encodeURIComponent(requestId)}`,
            { headers: { "X-Glove-Agent-Key": agentKey } }
          );
          if (!statusRes.ok) continue;

          const status = await statusRes.json();
          if (status?.status === "approved") return;
          if (status?.status === "denied") {
            return { block: true, blockReason: `Denied in Glove: ${requestId}` };
          }
          if (status?.status === "expired") {
            return { block: true, blockReason: `Approval expired: ${requestId}` };
          }
        } catch {
          // Keep polling until timeout.
        }
      }

      return { block: true, blockReason: `Approval timeout. Approve in Glove: ${uiUrl}` };
    },
    { priority: 100 }
  );
}
