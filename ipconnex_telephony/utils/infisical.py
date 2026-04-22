"""
Infisical client — pulls secrets from the IPCONNEX self-hosted Infisical instance.

Env vars expected on the bench:
  INFISICAL_URL            (e.g. https://infisical.example.com)
  INFISICAL_CLIENT_ID
  INFISICAL_CLIENT_SECRET

Per-call arguments (from Telephony Settings):
  project_slug   (e.g. "tenant-ipconnex")
  environment    (e.g. "prod")
  secret_key     (the key name stored in Infisical, e.g. "ACR_PASSWORD")

If any env var is missing, get_secret() returns None — callers should fall
back to the DocType password field. No exception is raised for absence; only
network/auth failures bubble up (and are logged with frappe.logger()).
"""

import os
import requests
import frappe


_TOKEN_CACHE = {"token": None, "expires_at": 0}


def get_secret(secret_key, project_slug, environment="prod"):
    url = os.environ.get("INFISICAL_URL")
    client_id = os.environ.get("INFISICAL_CLIENT_ID")
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET")

    if not (url and client_id and client_secret and secret_key and project_slug):
        return None

    try:
        token = _get_token(url, client_id, client_secret)
        workspace_id = _resolve_workspace_id(url, token, project_slug)
        if not workspace_id:
            frappe.logger().warning(f"Infisical: project slug {project_slug!r} not found")
            return None

        r = requests.get(
            f"{url.rstrip('/')}/api/v3/secrets/raw/{secret_key}",
            params={"workspaceId": workspace_id, "environment": environment},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 404:
            frappe.logger().warning(f"Infisical: secret {secret_key!r} not found in {project_slug}/{environment}")
            return None
        r.raise_for_status()
        return r.json()["secret"]["secretValue"]
    except Exception as e:
        frappe.logger().error(f"Infisical lookup failed ({secret_key}): {e}")
        return None


def _get_token(url, client_id, client_secret):
    import time
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > time.time() + 60:
        return _TOKEN_CACHE["token"]

    r = requests.post(
        f"{url.rstrip('/')}/api/v1/auth/universal-auth/login",
        json={"clientId": client_id, "clientSecret": client_secret},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    _TOKEN_CACHE["token"] = data["accessToken"]
    _TOKEN_CACHE["expires_at"] = time.time() + int(data.get("expiresIn", 2592000))
    return _TOKEN_CACHE["token"]


def _resolve_workspace_id(url, token, project_slug):
    r = requests.get(
        f"{url.rstrip('/')}/api/v2/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    for ws in r.json().get("workspaces", []):
        if ws.get("slug") == project_slug or ws.get("name") == project_slug:
            return ws["id"]
    return None
