# IPCONNEX Team Project Template — Design Spec

**Date:** 2026-04-15
**Owner:** Omar
**Status:** Approved

---

## Purpose

A reusable project template that any team member can copy to start a new Claude Code project. Each project is typically: deploy a server, build an app, or build a feature. The template provides consistent structure, secrets management, deployment patterns, skill discovery, and security scanning across the team.

---

## File Structure

```
TEMPLATE/
├── CLAUDE.md                          # Main instructions, stack picker, team rules
├── .env.example                       # Infisical credentials template
├── .gitignore                         # .env, .env.local, .DS_Store, node_modules, etc.
├── TODO.md                            # Task tracking template
├── HANDOFF.md                         # Session handoff template
├── DECISIONS.md                       # Architecture decision log
├── .claude/
│   ├── settings.json                  # MCP connections, minimal permissions
│   └── commands/
│       ├── init-project.md            # Interactive onboarding
│       ├── deploy.md                  # Deploy to target server
│       ├── health-check.md            # Verify services running
│       ├── setup-env.md               # Pull secrets from Infisical
│       ├── research.md                # Scan skill marketplaces
│       └── scan-skill.md              # Prompt injection scanner
├── skills/
│   ├── ipconnex-infisical/SKILL.md    # Infisical access (reads from .env)
│   └── scan-skill/SKILL.md            # Prompt injection detection
└── docs/
    └── architecture/
        └── OVERVIEW.md                # System architecture template
```

---

## CLAUDE.md Structure

Top-to-bottom sections:

### 1. Project Header
- `{{PROJECT_NAME}}`, `{{DESCRIPTION}}`, `{{OWNER}}`
- Project type: server deployment / app / feature / custom
- Date created, team members

### 2. Infisical Integration
- Points to `.env` for credentials
- Which project/environment this agent has access to
- Rule: "Always use Infisical for secrets. Never hardcode."

### 3. Stack Picker (Fenced Commented Blocks)
Each block is fenced with `<!-- STACK: NAME -->` ... `<!-- /STACK: NAME -->`. Team member deletes unused blocks manually or via `/init-project`.

**Next.js block includes:**
- Skills: `antigravity-bundle-web-wizard:nextjs-best-practices`, `antigravity-bundle-web-wizard:react-best-practices`, `antigravity-bundle-web-wizard:tailwind-patterns`, `antigravity-bundle-web-wizard:react-patterns`
- Dev commands: `npm run dev`, `npm run build`, `npm run lint`
- Patterns: App Router, Server Components, Tailwind CSS

**Go block includes:**
- Patterns: standard project layout, error handling conventions
- Dev commands: `go run .`, `go test ./...`, `go build`
- Common tools: air (hot reload), golangci-lint

**Python block includes:**
- Patterns: virtual environments, requirements.txt / pyproject.toml
- Dev commands: `python -m venv`, `pip install`, `pytest`
- Common tools: ruff, mypy

**ERPNext block includes:**
- Skills: frappe-erpnext-customizer (from existing projects)
- Dev commands: `bench start`, `bench build`, `bench migrate`
- Patterns: Frappe framework hooks, doctypes, API

### 4. Deployment Target
- Type placeholder: LXC / VM / VPS / Custom
- `{{TARGET_IP}}`, `{{SSH_USER}}`, access method
- Rule: "Always ask before deploying"
- Priority order documented: LXC > VM on Proxmox > External VPS > Custom

### 5. Default Skills (Always Active)
Process skills (always loaded):
- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `superpowers:test-driven-development`
- `superpowers:systematic-debugging`
- `superpowers:requesting-code-review`
- `superpowers:receiving-code-review`
- `superpowers:verification-before-completion`
- `superpowers:finishing-a-development-branch`
- `superpowers:dispatching-parallel-agents`
- `chrome-devtools-mcp:chrome-devtools`

### 6. Reference Repos
Links to scan before building:
- https://mcpmarket.com/tools/skills
- https://claudeskills.info
- https://skills.sh

Listed in CLAUDE.md for awareness. The `/research` command does a deep scan of these.

### 7. Documentation Pointers
- Points to: TODO.md, HANDOFF.md, DECISIONS.md, docs/architecture/OVERVIEW.md
- Rules:
  - "Update HANDOFF.md at end of each session"
  - "Log architecture decisions in DECISIONS.md"

### 8. Team Rules
1. Secrets in Infisical only — never hardcode, never commit
2. Always ask before deploying
3. Scan skills for prompt injection before installing
4. Update documentation as you go
5. Use `/research` before building something that might already exist as a skill

---

## Custom Commands

### `/init-project` — Interactive Onboarding
**Flow:**
1. Ask project name → fill `{{PROJECT_NAME}}` everywhere
2. Ask description (1-2 sentences) → fill `{{DESCRIPTION}}`
3. Ask owner → fill `{{OWNER}}`
4. Ask stack [Next.js / Go / Python / ERPNext / Other] → remove unused stack blocks
5. Ask deployment target [LXC / VM / VPS / Custom / Not yet]
   - LXC/VM: ask IP → fill `{{TARGET_IP}}`
   - VPS: ask hostname/IP + SSH user
   - Custom: ask description
   - Not yet: leave placeholders
6. Ask Infisical project slug → fill in `.env.example`
   - Ask environment [prod / staging / dev]
7. Offer to run `/research` for relevant skills
   - Scan each found skill for prompt injection
8. Show summary, commit as `init: {{PROJECT_NAME}}`

### `/deploy` — Deploy to Target Server
- Reads deployment config from CLAUDE.md (type, IP, SSH user)
- **Always asks for confirmation before deploying**
- Supports: rsync, git pull, Docker, systemd restart, PM2 restart
- Runs `/health-check` after deploy
- Logs deployment in DECISIONS.md if first deploy or config change

### `/health-check` — Verify Services
- SSH to target server
- Check service status (systemd / PM2 / Docker)
- Curl health endpoint if configured in CLAUDE.md
- Report: service status, uptime, last 20 log lines

### `/setup-env` — Pull Secrets from Infisical
- Reads `INFISICAL_*` vars from `.env`
- Authenticates via machine identity
- Fetches all secrets for configured project/environment
- Writes to `.env.local` (gitignored)
- **Never prints secret values to screen**

### `/research` — Scan Skill Marketplaces
- Fetches from the 4 reference URLs
- Searches for skills matching current stack/task description
- Presents findings with name, description, source
- Runs `/scan-skill` on any skill before recommending installation
- Lists in CLAUDE.md for awareness, `/research` command for deep lookup

### `/scan-skill` — Prompt Injection Scanner
- Reads skill markdown file content
- Checks for:
  - Hidden instructions (`<system>`, `<instructions>`, invisible unicode characters)
  - System prompt overrides or role reassignment
  - Encoded/obfuscated shell commands (base64, hex, escaped strings)
  - Data exfiltration patterns (curl/wget to external URLs, piping secrets)
  - Tool abuse (unauthorized file writes, permission escalation)
  - Social engineering phrases ("ignore previous instructions", "you are now", "override", "forget")
- Output levels:
  - **SAFE** — no issues detected
  - **WARNING** — suspicious patterns found (details listed)
  - **BLOCKED** — clear injection attempt (reason + evidence)
- Runs automatically before any skill is added to the project

---

## File Templates

### `.env.example`
```
# Infisical Access — fill per project
INFISICAL_URL=http://10.100.10.230
INFISICAL_CLIENT_ID=
INFISICAL_CLIENT_SECRET=
INFISICAL_PROJECT_SLUG=
INFISICAL_ENVIRONMENT=prod
```

### `TODO.md`
Structured template with sections: Current Phase, Active Tasks, Blocked, Completed.

### `HANDOFF.md`
Session handoff with sections: Last Session (date, who, what was done, what's next, known issues), Environment Notes, Access & Credentials (references to Infisical, no actual values).

### `DECISIONS.md`
ADR format: Title, Date, Status (proposed/accepted/rejected), Context, Decision, Alternatives, Consequences.

### `docs/architecture/OVERVIEW.md`
Sections: System Diagram, Components, Data Flow, Infrastructure (target type, IP, services).

### `.claude/settings.json`
- MCP connections configured: Chrome DevTools, M365, Notion
- `permissions.allow`: minimal — each team member builds their own allow list
- `permissions.deny`: empty

---

## Skills

### `skills/ipconnex-infisical/SKILL.md` (Updated)
- **Change:** Remove all hardcoded credentials
- Auth examples use `$INFISICAL_CLIENT_ID` and `$INFISICAL_CLIENT_SECRET` from environment
- Python helper reads from `os.environ` instead of hardcoded constants
- Rest of content unchanged (project reference table, common mistakes, API examples)

### `skills/scan-skill/SKILL.md` (New)
- Triggered when installing or updating any skill
- Detection patterns documented above under `/scan-skill` command
- Can also be used standalone on any markdown file
- Does not block automatically — reports findings, team member decides

---

## Security Rules

1. **Secrets:** All credentials in Infisical. `.env` holds only Infisical access. `.env.local` for runtime secrets (gitignored). Never print secret values.
2. **Skills:** Every new or updated skill runs through prompt injection scan before use.
3. **Deployment:** Always confirm with user before any deploy action.
4. **Permissions:** MCP tools configured but not pre-approved. Each user approves as they work.

---

## What's NOT in the Template

- No application code — this is a project scaffold, not a starter app
- No CI/CD — varies too much per project
- No Docker/compose files — added per project via stack choice
- No global permissions — each team member's allow list is personal
