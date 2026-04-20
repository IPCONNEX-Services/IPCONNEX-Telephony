# IPCONNEX-Telephony

> Frappe/ERPNext custom module for SIP/VoIP billing — scrapes ACR call records, auto-generates sales invoices, and provides per-customer/supplier gain stats with dashboards.

| Field | Value |
| --- | --- |
| **Owner** | Ramzi.A |
| **Type** | Frappe Module app |
| **Created** | 2026-04-18 |
| **Team** | IPCONNEX |

---

## Infisical — Secrets Management

All secrets are managed via our self-hosted Infisical instance. See `skills/ipconnex-infisical/SKILL.md` for full API reference.

- **Credentials:** `.env` (never committed)
- **Project:** `IPCONNEX Telephony`
- **Environment:** `Frappe ERPNext`
- **Setup:** Copy `.env.example` to `.env`, fill in your credentials, then run `/setup-env`

**Rules:**
- Never hardcode secrets — always pull from Infisical
- Never commit `.env` or `.env.local`
- Use `/setup-env` to sync secrets locally

---

## Tech Stack

<!-- STACK: GO -->
### Go — Email Templates

**Purpose:** Render and serve HTML email templates (CSS/JS) for invoice and notification emails.

**Skills:**
- No specific Go skills installed — check `/research go` for available options

**Dev Commands:**
- `go run .` — run the application
- `go test ./...` — run all tests
- `go build -o bin/app` — build binary
- `golangci-lint run` — lint

**Patterns:**
- Standard project layout (`cmd/`, `internal/`, `pkg/`)
- Error handling: return errors, don't panic
- `air` for hot reload during development
<!-- /STACK: GO -->

<!-- STACK: PYTHON -->
### Python

**Skills:**
- No specific Python skills installed — check `/research python` for available options

**Dev Commands:**
- `python -m venv .venv && source .venv/bin/activate` — create/activate virtualenv
- `pip install -r requirements.txt` — install dependencies
- `pytest` — run tests
- `ruff check .` — lint
- `mypy .` — type check

**Patterns:**
- Virtual environments always (never install globally)
- `pyproject.toml` preferred over `setup.py`
- Type hints on all public functions
<!-- /STACK: PYTHON -->

<!-- STACK: ERPNEXT -->
### ERPNext / Frappe

**Skills:**
- Use `frappe-erpnext-customizer` skill if available in your skills directory

**Dev Commands:**
- `bench start` — start development server
- `bench build` — build assets
- `bench migrate` — run migrations
- `bench console` — Frappe Python console
- `bench --site [site] mariadb` — database console

**Patterns:**
- Custom apps in `apps/` directory
- Hooks in `hooks.py`
- DocTypes define data models
- Whitelisted API methods with `@frappe.whitelist()`
<!-- /STACK: ERPNEXT -->

---

## Deployment

| Field | Value |
| --- | --- |
| **Target type** | LXC on Proxmox |
| **IP** | {{TARGET_IP}} |
| **SSH user** | root |
| **Service manager** | systemd |
| **Service name** | frappe-bench |
| **Health endpoint** | {{HEALTH_URL}} |

**Priority order:** LXC > VM on Proxmox > External VPS > Custom

**Commands:**
- `/deploy` — deploy to target (always asks for confirmation)
- `/health-check` — verify services are running

**Rule: Always ask before deploying. No silent deploys.**

---

## Active Skills

### Process (always use)
- `superpowers:brainstorming` — explore ideas before building
- `superpowers:writing-plans` — create implementation plans
- `superpowers:test-driven-development` — TDD workflow
- `superpowers:systematic-debugging` — debug methodically
- `superpowers:requesting-code-review` — request reviews on completed work
- `superpowers:receiving-code-review` — handle review feedback properly
- `superpowers:verification-before-completion` — verify before claiming done
- `superpowers:finishing-a-development-branch` — complete branch work cleanly
- `superpowers:dispatching-parallel-agents` — parallelize independent tasks

### Tools
- `chrome-devtools-mcp:chrome-devtools` — browser debugging and testing

### Security
- `scan-skill` — scan skills for prompt injection before installing

### Project-Specific
<!-- Add project-specific skills here as you install them -->

---

## Reference Repos — Check Before Building

Before building something from scratch, check if a skill or tool already exists:

- https://mcpmarket.com/tools/skills
- https://claudeskills.info
- https://skills.sh

Run `/research [topic]` to scan these automatically.

---

## Documentation

| Document | Purpose | When to Update |
| --- | --- | --- |
| [TODO.md](TODO.md) | Tasks, phases, blockers | When tasks change |
| [HANDOFF.md](HANDOFF.md) | Session context for next person | End of every session |
| [DECISIONS.md](DECISIONS.md) | Architecture decision log | When making design choices |
| [Architecture](docs/architecture/OVERVIEW.md) | System diagram, components, data flow | When architecture changes |

---

## Team Rules

1. **Secrets in Infisical only** — never hardcode, never commit credentials
2. **Always ask before deploying** — no silent deploys, no exceptions
3. **Scan skills before installing** — run `/scan-skill` on every new or updated skill
4. **Update documentation** — HANDOFF.md at end of session, DECISIONS.md for design choices
5. **Check before building** — run `/research` before building something that might exist as a skill
