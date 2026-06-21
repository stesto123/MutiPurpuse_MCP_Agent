# Secret Handling

## Storage Rules

Store real credentials outside the repository. Recommended locations:

- private config: `~/.config/ai-scout`
- secret files: `~/.config/ai-scout/secrets`
- runtime data: `~/.local/share/ai-scout`
- OS secret store where supported by the MCP server

Set restrictive permissions for local secret directories:

```sh
chmod 700 ~/.config/ai-scout ~/.config/ai-scout/secrets
chmod 600 ~/.config/ai-scout/secrets/*
```

## What Counts as a Secret

Treat these as secrets or private data:

- API keys and bearer tokens
- OAuth client secrets and refresh tokens
- service account files
- private calendar IDs and account IDs
- generated reports that contain personal scheduling context
- local memory and deduplication state

## Configuration Pattern

Committed config files should contain placeholders only. Private config files
may reference secret file paths, environment variable names, or OS secret-store
keys, but should avoid embedding raw token values.

Example placeholder pattern:

```yaml
secrets:
  - name: "github_token"
    mount_path: "/run/host-secrets/github_token"
    source: "host_file"
```

## Docker Compose

The Compose template expects host paths from `.env`:

- `AI_SCOUT_HOST_CONFIG_DIR`
- `AI_SCOUT_HOST_DATA_DIR`
- `AI_SCOUT_HOST_SECRETS_DIR`

The `.env` file should contain paths, not secret values. The Docker image should
never copy secret files at build time.

## launchd

The launchd template should contain local paths and mode settings only. Do not
put tokens or OAuth refresh credentials in plist environment variables. Use
private config files or OS secret stores read by MCP servers.

## Rotation

Rotate credentials when:

- a secret is accidentally committed or logged
- a laptop, backup, or secret file may be compromised
- an MCP server changes its requested scopes
- autonomous mode performs unexpected writes

After rotation, restart in dry-run mode and verify reports before enabling
autonomous mode again.
