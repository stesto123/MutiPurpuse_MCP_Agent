# Local Runtime Operations

## Current Status

The repository currently provides an initial `ai-scout` CLI plus local runtime
templates. The commands below describe the local setup and runtime contract the
implementation should preserve.

## Private Local Directories

Use Python 3.10+ for the installed runtime. The project uses `uv` for the
reproducible developer environment and lockfile.

Create private config and data directories outside the repository:

```sh
mkdir -p ~/.config/ai-scout/secrets
mkdir -p ~/.local/share/ai-scout/{memory,reports,runs}
chmod 700 ~/.config/ai-scout ~/.config/ai-scout/secrets
```

Copy examples into the private config directory, then edit the private copies:

```sh
cp config/profiles/local.example.yaml ~/.config/ai-scout/profile.yaml
cp config/policies/scout-policy.example.yaml ~/.config/ai-scout/policy.yaml
cp config/sources/ai-sources.example.yaml ~/.config/ai-scout/sources.yaml
cp config/mcp/servers.example.yaml ~/.config/ai-scout/mcp.yaml
```

Do not edit real tokens or personal account values into committed example
files.

## Environment File

For Docker Compose, copy the environment template and replace placeholder paths:

```sh
cp .env.example .env
```

The `.env` file is ignored by Git. It should contain local paths only, not API
keys or OAuth tokens.

## Dry-Run Mode

Dry-run mode (`dry_run`) is the default. It may read external resources through allowed MCP
tools and write local reports, but it should not write local memory or create
calendar events.

CLI shape:

```sh
python3 -m ai_scout run \
  --mode dry_run \
  --config-dir ~/.config/ai-scout \
  --data-dir ~/.local/share/ai-scout
```

If the package is installed, `ai-scout run --mode dry_run` is equivalent. From
the source checkout, `./scripts/run-dry.sh` uses the same runtime path.

## Autonomous Mode

Autonomous mode can write memory and calendar events through MCP tools when the
policy allows it. It should require:

- `AI_SCOUT_MODE=autonomous`
- `AI_SCOUT_AUTONOMOUS_CONFIRM=I_UNDERSTAND_AUTONOMOUS_SIDE_EFFECTS`
- enabled source entries and MCP servers in private local config
- working rollback notes in the generated run report

Start with dry-run reports until the planned writes are predictable.

## Docker Compose

After editing `.env`, run the local container template:

```sh
docker compose --env-file .env -f infra/compose/docker-compose.example.yaml run --rm ai-scout
```

The Compose template mounts:

- private config from `AI_SCOUT_HOST_CONFIG_DIR`
- runtime data from `AI_SCOUT_HOST_DATA_DIR`
- private secret files from `AI_SCOUT_HOST_SECRETS_DIR`
- private MCP config from `AI_SCOUT_HOST_CONFIG_DIR/mcp.yaml`

Secrets are mounted at runtime and are not copied into the image.

## launchd Schedule

To schedule local runs on macOS:

```sh
mkdir -p ~/Library/Logs/ai-scout
cp infra/launchd/com.example.ai-scout.plist.template ~/Library/LaunchAgents/com.example.ai-scout.plist
plutil -lint ~/Library/LaunchAgents/com.example.ai-scout.plist
```

Edit the copied plist and replace every `/Users/YOUR_USER` placeholder. Then
load and enable it:

```sh
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.example.ai-scout.plist
launchctl enable "gui/$(id -u)/com.example.ai-scout"
launchctl kickstart -k "gui/$(id -u)/com.example.ai-scout"
```

To stop scheduled runs:

```sh
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.example.ai-scout.plist
```

## Logs and Reports

Use local logs for process health and run reports for decision auditing:

- launchd stdout: `~/Library/Logs/ai-scout/launchd.out.log`
- launchd stderr: `~/Library/Logs/ai-scout/launchd.err.log`
- reports: `~/.local/share/ai-scout/reports`
- run state: `~/.local/share/ai-scout/runs`
