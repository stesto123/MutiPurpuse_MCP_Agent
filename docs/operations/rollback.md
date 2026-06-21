# Rollback Runbook

## Scope

Rollback applies to local memory, run reports, and external side effects created
through MCP tools. The current repository provides templates only; automated
rollback tooling is not implemented yet.

## Stop New Runs

Stop scheduled or containerized runs before changing state:

```sh
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.example.ai-scout.plist
docker compose --env-file .env -f infra/compose/docker-compose.example.yaml down
```

If a process is still running, terminate it normally first so it can flush its
current report.

## Identify the Run

Use the JSON or Markdown report from `~/.local/share/ai-scout/reports` to find:

- run ID and timestamp
- mode used for the run
- MCP tool calls made
- local memory records written
- calendar event IDs created
- scoring and scheduling reasons

Dry-run reports should not contain external writes.

## Restore Local Data

Before enabling autonomous mode, keep timestamped backups:

```sh
cp -a ~/.local/share/ai-scout ~/.local/share/ai-scout.backup-YYYYMMDD-HHMMSS
```

To roll back local state, stop the agent and restore the relevant backup:

```sh
rm -rf ~/.local/share/ai-scout
cp -a ~/.local/share/ai-scout.backup-YYYYMMDD-HHMMSS ~/.local/share/ai-scout
```

If no backup exists, remove only the records listed in the run report and keep a
copy of the original files for investigation.

## Reverse Calendar Writes

Calendar changes must be reversed through the configured MCP calendar server,
not by direct provider APIs from agent code. Use the event IDs and rationale in
the run report to delete or update only events created by the affected run.

The implementation should make calendar writes idempotent by storing:

- provider event ID
- run ID
- source candidate ID
- event title and planned time
- creation timestamp

## Revoke or Rotate Secrets

If a secret may have been exposed:

1. Stop all scheduled runs.
2. Revoke or rotate the credential in the provider or OS secret store.
3. Replace the local secret file under `~/.config/ai-scout/secrets`.
4. Check reports and logs for accidental secret leakage.
5. Restart only in dry-run mode.

## Resume

Resume autonomous mode only after dry-run mode produces expected candidates,
scores, and planned side effects. Keep the rollback report and any manual fixes
with local operational notes, not in the public repository.
