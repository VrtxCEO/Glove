# Glove Safety Shell

Glove is a policy and approval service that sits between OpenClaw and sensitive actions.
OpenClaw asks Glove for permission. Glove returns:

- `allow`
- `deny`
- `require_pin`

If `require_pin`, Glove creates an approval request and waits for a human PIN approval.

## How Glove Works (Exact Flow)

1. OpenClaw sends a request to Glove:
   - `action`
   - `target`
   - `metadata`
2. Glove evaluates risk:
   - blocked targets/rules in `policy.json`
   - dynamic risk keywords from admin UI
3. Glove decides:
   - low/medium -> `allow`
   - explicit deny rule -> `deny`
   - high risk/keyword match -> `require_pin`
4. For `require_pin`, Glove creates `request_id`, expiration, audit entry, and `ui_url`.
5. User opens `ui_url`, PIN form auto-fills `request_id`, user approves.
6. OpenClaw polls Glove status endpoint.
7. When status becomes `approved`, OpenClaw continues automatically.

## Security Model

Glove uses separate credentials:

- `agent key`: OpenClaw can only call agent endpoints.
- `admin key`: only admins can configure PIN, risk keywords, extensions, audit.

OpenClaw should never have admin key.

PIN security:

- stored as salted PBKDF2 hash
- attempt counter + lockout (`GLOVE_MAX_PIN_ATTEMPTS`)
- every attempt audited

Audit log:

- append-only style with hash chaining (`prev_hash` -> `entry_hash`)

## Risk Classification

High risk is determined by:

1. `policy.json` rules (`action_prefix`, `risk`, `decision`)
2. Admin-defined **Risk Keywords** (UI/API)

If any risk keyword appears in request `action`, `target`, or `metadata`, Glove forces:

- `decision = require_pin`
- `policy_id = policy-risk-keyword`

## Request Lifecycle

Request statuses:

- `pending`
- `approved`
- `denied`
- `expired`

OpenClaw-side behavior:

- on `require_pin`, OpenClaw waits (polls status endpoint)
- resumes on `approved`
- aborts on `denied` / `expired` / timeout

## Approval URL Behavior

Glove returns `ui_url` for each `require_pin` request:

- default base: `GLOVE_PUBLIC_URL`
- optional override per request: `metadata.ui_base_url`
- request ID auto-injected as `?request_id=...`

UI auto-fills request ID from query string.

## Web UI

Main features:

- admin key entry
- PIN setup and approval
- pending request list
- audit viewer
- risk keyword editor
- extension discovery/install/enable/test

Logo path:

- `Glove/glove/static/logo.png`

## API Endpoints

Agent endpoints (`X-Glove-Agent-Key`):

- `POST /api/v1/agent/request`
- `GET /api/v1/agent/request-status?request_id=<id>`

Admin endpoints (`X-Glove-Admin-Key`):

- `POST /api/v1/admin/setup-pin`
- `POST /api/v1/admin/approve-pin`
- `GET /api/v1/admin/requests/pending`
- `GET /api/v1/admin/audit/recent`
- `GET /api/v1/admin/risk-keywords`
- `POST /api/v1/admin/risk-keywords/config`
- extension endpoints (`/api/v1/admin/extensions/*`)

Inbound approval webhook:

- `POST /api/v1/inbound/reply?token=<GLOVE_INBOUND_TOKEN>`
- parses `PIN <request_id> <pin>`

## OpenClaw Integration

OpenClaw C++ client files:

- `OpenClaw/GloveClient.h`
- `OpenClaw/GloveClient.cpp`

Startup hook:

- `OpenClaw/main.cpp`

Env vars used by OpenClaw process:

- `GLOVE_BASE_URL`
- `GLOVE_AGENT_KEY`

## Configuration

Primary env vars:

- `GLOVE_HOST`
- `GLOVE_PORT`
- `GLOVE_PUBLIC_URL`
- `GLOVE_DB_PATH`
- `GLOVE_POLICY_PATH`
- `GLOVE_AGENT_KEY`
- `GLOVE_ADMIN_KEY`
- `GLOVE_INBOUND_TOKEN`
- `GLOVE_REQUEST_TTL_SECONDS`
- `GLOVE_MAX_PIN_ATTEMPTS`

Risk/signature-related:

- `GLOVE_CLAWHUB_TRUST_STORE_PATH`
- `GLOVE_REQUIRE_EXTENSION_SIGNATURES`

Notifier:

- `GLOVE_NOTIFIER_PROVIDER` or `GLOVE_NOTIFIER_PROVIDERS`

## Extensions

Glove supports extension-driven notifications and testing via:

- `Glove/extensions/<id>/glove-extension.json`

Extension install supports:

- ZIP URL install
- ZIP upload install
- optional replace

When signature enforcement is enabled, install requires:

- `key_id`
- `signature_b64` (Ed25519 signature of SHA-256 hex of ZIP bytes)
- trusted key in `trusted_publishers.json`

## Quick Start (Windows)

From repo root (`OpenClaw/`):

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_glove_windows.ps1
```

Start Glove:

```powershell
powershell -ExecutionPolicy Bypass -File .\Glove\scripts\run_glove.ps1
```

Start OpenClaw with agent-only env:

```powershell
powershell -ExecutionPolicy Bypass -File .\Glove\scripts\run_openclaw_with_glove.ps1
```

Open UI:

- `http://127.0.0.1:8088/`

## Build Standalone Bundle

```powershell
powershell -ExecutionPolicy Bypass -File .\Glove\scripts\build_windows_bundle.ps1
```

Output:

- `Glove/dist/Glove-Windows/`
- `Glove/dist/Glove-Windows.zip`

## Hardening Checklist

1. Run Glove as separate service/user.
2. Keep admin key out of OpenClaw process.
3. Use HTTPS/reverse proxy for remote access.
4. Keep `.env.local.ps1` private.
5. Keep signatures enabled for extension installs.

## License

Glove is licensed under GNU GPL v3.0. See:

- `Glove/LICENSE`

## Terms of Service

Use of Glove is subject to:

- `Glove/TERMS.md`
