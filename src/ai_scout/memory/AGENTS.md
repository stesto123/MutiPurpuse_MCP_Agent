# Memory Instructions

## Scope

This directory owns persistent local state, resource history, run history,
deduplication records, and calendar side-effect records.

## Rules

- Keep memory portable and local-first.
- Do not store secrets in memory.
- Store enough metadata to explain why a resource was accepted, rejected, or
  scheduled.
- Calendar writes must be idempotent and traceable to a resource ID and run ID.
- Prefer append-only records for audit logs.
- If schema migrations are introduced, make them explicit and testable.

## Sensitive Data

- Avoid storing full personal calendar details unless needed for scheduling.
- Do not store OAuth token payloads, refresh tokens, private cookies, or browser
  session files.
