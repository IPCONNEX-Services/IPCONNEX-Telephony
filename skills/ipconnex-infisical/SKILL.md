---
name: ipconnex-infisical
description: Use when an agent needs to fetch, read, or write infrastructure or tenant secrets for the IPCONNEX environment. Applies whenever credentials, API keys, passwords, tokens, or connection strings are needed to interact with any IPCONNEX service — hypervisors, network gear, tenant ERPs, apps, or storage.
---

# IPCONNEX Infisical — Secret Access

## Overview

Self-hosted Infisical instance for the IPCONNEX datacenter infrastructure. All credentials previously in `.env` now live here. Use the machine identity configured in your project's `.env` to authenticate.

**URL:** Configured via `INFISICAL_URL` in `.env` — internal only, requires SSL-VPN or VLAN10 access.

**Prerequisites:** Copy `.env.example` to `.env` and fill in your Infisical credentials before using any commands below.

---

## Quick Auth (copy-paste)

```bash
# Load credentials from .env
source .env

# Authenticate with machine identity
ACCESS_TOKEN=$(curl -s -X POST "$INFISICAL_URL/api/v1/auth/universal-auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"clientId\":\"$INFISICAL_CLIENT_ID\",\"clientSecret\":\"$INFISICAL_CLIENT_SECRET\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")
```

Token is valid for 30 days. No second step needed for machine identity auth (unlike human login).

---

## Fetch All Secrets from a Project

```bash
# 1. Get all workspace IDs
curl -s "$INFISICAL_URL/api/v2/workspaces" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python3 -c "import sys,json; [print(w['id'], w['name']) for w in json.load(sys.stdin)['workspaces']]"

# 2. Fetch secrets from a project (replace WORKSPACE_ID and use 'prod' environment)
curl -s "$INFISICAL_URL/api/v3/secrets/raw?workspaceId=WORKSPACE_ID&environment=prod" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python3 -c "import sys,json; [print(s['secretKey'],'=',s['secretValue']) for s in json.load(sys.stdin)['secrets']]"
```

## Fetch a Single Secret

```bash
curl -s "$INFISICAL_URL/api/v3/secrets/raw/SECRET_KEY?workspaceId=WORKSPACE_ID&environment=prod" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['secret']['secretValue'])"
```

## Set / Update a Secret

```bash
# Create (POST) or update (PATCH) a secret
curl -s -X POST "$INFISICAL_URL/api/v3/secrets/raw/MY_KEY" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"workspaceId\":\"WORKSPACE_ID\",\"environment\":\"prod\",\"secretValue\":\"my-value\",\"type\":\"shared\"}"
```

Use `PATCH` instead of `POST` to update an existing secret.

---

## Projects Reference

| Project | Environment(s) | Contains |
| --- | --- | --- |
| `infra-network` | prod | FortiGate API key, WireGuard VPS, NPM admin |
| `infra-hypervisors` | prod | Proxmox S2 token, nested Proxmox token, ESXi root |
| `infra-storage` | prod | OVH API keys, NAS SSH, PBS credentials |
| `infra-apps` | prod | NetBox API key, Infisical own credentials, ai_agent identity |
| `tenant-cornelia` | prod, staging | ERP admin, LXC IPs/passwords |
| `tenant-ecf` | prod, staging | ERPNext 14 admin, LXC IP |
| `tenant-sante-direct` | prod, staging | ERPNext 15 admin, LXC IP |
| `tenant-algeria-projects` | prod | ERPNext 15 admin, LXC IP |
| `tenant-qtsi` | prod | ERPNext 16, Next.js, LXC credentials |
| `tenant-fonotel` | prod | SIP switch SSH, Gate103 RDP |
| `tenant-ipconnex` | prod | Sales invoice, wg-admin credentials |

**Note:** Each project auto-created 3 environments (`dev`, `staging`, `prod`). Active secrets are in `prod`. Use `staging` for tenant test environments.

---

## Credentials Setup

Your `.env` file should contain:

```
INFISICAL_URL=http://10.100.10.230
INFISICAL_CLIENT_ID=your-client-id-here
INFISICAL_CLIENT_SECRET=your-client-secret-here
INFISICAL_PROJECT_SLUG=your-project
INFISICAL_ENVIRONMENT=prod
```

Get these values from your team lead or from the `infra-apps` project in Infisical under the machine identity assigned to your agent.

---

## Python Helper (for scripts/agents that need multiple secrets)

```python
import os
import requests

INFISICAL_URL = os.environ["INFISICAL_URL"]
CLIENT_ID = os.environ["INFISICAL_CLIENT_ID"]
CLIENT_SECRET = os.environ["INFISICAL_CLIENT_SECRET"]

def get_token():
    r = requests.post(f"{INFISICAL_URL}/api/v1/auth/universal-auth/login",
                      json={"clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET})
    return r.json()["accessToken"]

def get_secrets(workspace_id: str, environment: str = "prod") -> dict:
    token = get_token()
    r = requests.get(f"{INFISICAL_URL}/api/v3/secrets/raw",
                     params={"workspaceId": workspace_id, "environment": environment},
                     headers={"Authorization": f"Bearer {token}"})
    return {s["secretKey"]: s["secretValue"] for s in r.json()["secrets"]}

def get_workspace_id(name: str) -> str:
    token = get_token()
    r = requests.get(f"{INFISICAL_URL}/api/v2/workspaces",
                     headers={"Authorization": f"Bearer {token}"})
    matches = [w for w in r.json()["workspaces"] if w["name"] == name]
    return matches[0]["id"] if matches else None

# Usage
ws_id = get_workspace_id("infra-network")
secrets = get_secrets(ws_id)
fortigate_key = secrets["FORTIGATE_API_KEY"]
```

---

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| Using human login flow (two-step) | Machine identity uses `/api/v1/auth/universal-auth/login` — single step, no org selection needed |
| Wrong environment slug | Use `prod` not `production` — Infisical auto-created slugs as `dev/staging/prod` |
| 401 on secret fetch | Token expired (30d TTL) — re-authenticate |
| Can't reach Infisical URL | Must be on SSL-VPN or VLAN10 — not reachable from public internet |
| Secret not found in project | Check if it was empty in `.env` at import time — 10 secrets were skipped (NAS, PBS, Fonotel RDP) |
| `.env` not loaded | Run `source .env` first, or ensure your script reads from environment |
