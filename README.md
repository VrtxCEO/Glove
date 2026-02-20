# Glove Safety Shell

Glove is a standalone approval and policy service for OpenClaw.

OpenClaw asks Glove for permission on sensitive actions. Glove returns:

- `allow`
- `deny`
- `require_pin`

When `require_pin`, Glove creates a request, gives a UI approval link, and waits for human PIN approval.

## What This Repo Contains

Standalone Glove service:

- FastAPI backend (`main.py`, `glove/`)
- admin web UI (`glove/static/index.html`)
- policy + audit + PIN approval flow
- installer/runner scripts (`scripts/`)

No OpenClaw game source is included in this repo.

## Quick Start (Windows)

From this repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

Start Glove:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_glove.ps1
```

Open UI:

- `http://127.0.0.1:8088/`

## Integrate With OpenClaw

OpenClaw must call Glove agent APIs.

### 1) Request decision

`POST /api/v1/agent/request` with header:

- `X-Glove-Agent-Key: <agent_key>`

Body:

```json
{
  "action": "file.write.savegame",
  "target": "C:\\Games\\OpenClaw\\SAVES.XML",
  "metadata": {
    "source": "openclaw",
    "ui_base_url": "http://192.168.1.25:8088"
  }
}
```

### 2) Handle decision

- `allow`: continue action
- `deny`: block action
- `require_pin`: show or relay returned `ui_url` to user

### 3) Wait for approval

Poll:

- `GET /api/v1/agent/request-status?request_id=<id>`

Status meanings:

- `pending`: keep waiting
- `approved`: continue
- `denied` / `expired`: stop action

## Approval UX

`ui_url` contains `?request_id=...`.

When user opens link:

1. request id auto-fills in UI
2. user enters PIN
3. request becomes `approved`
4. OpenClaw sees `approved` on status polling and continues

## High-Risk Rules

High risk is triggered by:

1. `policy.json` rule matches (`risk: high`)
2. Risk keywords from admin UI/API

If a risk keyword appears in action/target/metadata, Glove forces `require_pin`.

## Admin UI Features

- PIN setup / approval
- pending requests
- audit log
- risk keyword editor
- extension install/test/enable

Logo:

- put logo at `glove/static/logo.png`

## API Summary

Agent (`X-Glove-Agent-Key`):

- `POST /api/v1/agent/request`
- `GET /api/v1/agent/request-status?request_id=<id>`

Admin (`X-Glove-Admin-Key`):

- `POST /api/v1/admin/setup-pin`
- `POST /api/v1/admin/approve-pin`
- `GET /api/v1/admin/requests/pending`
- `GET /api/v1/admin/audit/recent`
- `GET /api/v1/admin/risk-keywords`
- `POST /api/v1/admin/risk-keywords/config`
- `GET/POST /api/v1/admin/extensions/*`

Inbound approval webhook:

- `POST /api/v1/inbound/reply?token=<GLOVE_INBOUND_TOKEN>`
- format: `PIN <request_id> <pin>`

## Optional OpenClaw Launcher Helper

If you want to launch an OpenClaw executable with agent-only env injection:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_openclaw_with_glove.ps1 -OpenClawExePath "C:\path\to\OpenClaw.exe"
```

## Build Standalone Bundle

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_bundle.ps1
```

Outputs:

- `dist/Glove-Windows/`
- `dist/Glove-Windows.zip`

## License and Terms

- License: `LICENSE` (GNU GPL v3.0)
- Terms: `TERMS.md`
