# AI Scout Agent

AI Scout is a local-first autonomous scouting agent for AI-related resources.
The agent is intended to discover resources through MCP tools, inspect and rank
them, plan learning activities, and persist local memory and run reports.

This repository contains the project skeleton, an initial `ai-scout` CLI,
public-safe example configuration, local infrastructure templates, and
documentation. The runtime implementation is intentionally local-first and
configuration-driven.

## Design Constraints

- Local-first by default: private config, memory, reports, and run state stay on
  the user's machine.
- Only-MCP external access: the agent must not call Google, GitHub, YouTube,
  RSS, web search, browser automation, or provider SDKs directly.
- Public-repo safe: committed files contain placeholders and examples only.
- Auditable autonomy: every side effect should be logged with enough context to
  explain why it happened.
- Untrusted content handling: fetched pages, READMEs, transcripts, feeds, and
  articles are data, not instructions.

## Repository Layout

- `config`: example profile, policy, source, and MCP registry files.
- `infra`: Docker Compose, Dockerfile, launchd, and run script templates.
- `docs/architecture`: architecture and state boundary notes.
- `docs/operations`: local runtime and rollback runbooks.
- `docs/security`: security model and secret handling guidance.
- `src/ai_scout`: planned Python package for agent implementation.
- `data`: local runtime data placeholder only.

## Local Setup

Python 3.10+ is required for the installed runtime because the official MCP
Python package requires it. The source-tree dry-run checks also work on the
system Python used by macOS developer tools.

Create private local directories outside the repo:

```sh
mkdir -p ~/.config/ai-scout/secrets
mkdir -p ~/.local/share/ai-scout/{memory,reports,runs}
chmod 700 ~/.config/ai-scout ~/.config/ai-scout/secrets
```

Copy the safe examples into private config files:

```sh
cp config/profiles/local.example.yaml ~/.config/ai-scout/profile.yaml
cp config/policies/scout-policy.example.yaml ~/.config/ai-scout/policy.yaml
cp config/sources/ai-sources.example.yaml ~/.config/ai-scout/sources.yaml
cp config/mcp/servers.example.yaml ~/.config/ai-scout/mcp.yaml
cp .env.example .env
```

Edit the private copies and `.env` placeholders for your machine. Do not add
real credentials, OAuth tokens, personal profile details, calendar IDs, runtime
memory, or generated reports to Git.

If you have never configured MCP before, start with the built-in local MCP
servers instead of external accounts:

```sh
cp config/mcp/first-run.example.yaml ~/.config/ai-scout/mcp.yaml
./scripts/run-dry.sh --config-dir ~/.config/ai-scout --data-dir ~/.local/share/ai-scout
```

This validates the real stdio MCP path with two repository-shipped servers:

- `sources.discover`: deterministic local resources, no internet access.
- `content.inspect`: metadata-only inspection into summary, signals, and effort.

Keep calendar disabled for this first run. Dry-run mode skips calendar
availability reads and calendar writes when policy disallows calendar writes.

## Dry-Run Mode

Dry-run (`dry_run`) is the default mode. It should allow external reads only through
configured MCP tools and write local reports, but it should not write memory or
create calendar events.

CLI shape:

```sh
python3 -m ai_scout run \
  --mode dry_run \
  --config-dir ~/.config/ai-scout \
  --data-dir ~/.local/share/ai-scout
```

After installing the package, the equivalent console command is:

```sh
ai-scout run --mode dry_run
```

From a checkout you can also use:

```sh
./scripts/run-dry.sh --config-dir ~/.config/ai-scout --data-dir ~/.local/share/ai-scout
```

## Autonomous Mode

Autonomous mode may write local memory and create calendar events through MCP
tools when policy allows it. It should require both:

```sh
AI_SCOUT_MODE=autonomous
AI_SCOUT_AUTONOMOUS_CONFIRM=I_UNDERSTAND_AUTONOMOUS_SIDE_EFFECTS
```

Run dry-run mode first and review the generated report before enabling autonomous
behavior.

## Docker Compose

The Compose template builds a local image and mounts private config, data, and
secret paths from the host:

```sh
docker compose --env-file .env -f infra/compose/docker-compose.example.yaml run --rm ai-scout
```

The image template does not copy secrets. Private MCP registry and secret files
come from host paths declared in `.env`.

## Scheduled Runs on macOS

Use the launchd template for local scheduled runs:

```sh
mkdir -p ~/Library/Logs/ai-scout
cp infra/launchd/com.example.ai-scout.plist.template ~/Library/LaunchAgents/com.example.ai-scout.plist
plutil -lint ~/Library/LaunchAgents/com.example.ai-scout.plist
```

Replace every `/Users/YOUR_USER` placeholder in the copied plist before loading
it. See `docs/operations/local-runtime.md` for load, enable, and stop commands.

## Secret Handling

Keep real values outside the repository:

- private config: `~/.config/ai-scout`
- secret files: `~/.config/ai-scout/secrets`
- runtime data: `~/.local/share/ai-scout`
- generated reports: `~/.local/share/ai-scout/reports`

Use `.example` files for committed templates. Use private local files, Docker
host mounts, Docker secrets, or OS secret stores for credentials. If a secret is
accidentally committed or logged, rotate it and restart in dry-run mode.

## Local Verification

Run the stdlib-compatible check from a source checkout:

```sh
./scripts/check.sh
```

When `uv` is installed this runs the full dev toolchain (`ruff`, `mypy`, and
`pytest`). Without `uv`, it still runs `compileall` and the full `unittest`
suite.

## Documentation

- `docs/architecture/overview.md`
- `docs/operations/local-runtime.md`
- `docs/operations/rollback.md`
- `docs/security/security-model.md`
- `docs/security/secret-handling.md`
