# Source Package Instructions

## Scope

These rules apply to implementation files under `src/ai_scout`.

## Code Boundaries

- Keep the package importable without real MCP servers or secrets.
- Do not perform network calls at import time.
- Do not read user-specific config at import time.
- Keep business logic separate from MCP transport details.
- Do not add direct SDK clients for external services unless they implement an
  MCP server or test fixture.

## Data Flow

- Prefer typed state objects and small pure functions for scoring, filtering,
  planning, and validation.
- Make every calendar write idempotent by carrying stable resource IDs and run
  IDs through the graph.
- Return structured errors from boundary layers so graph nodes can retry or
  degrade gracefully.

## Observability

- Log tool names, decision IDs, resource IDs, scores, and final side effects.
- Redact URLs only when they contain credentials or private tokens.
- Never log raw OAuth tokens, client secrets, refresh tokens, or local secret
  file contents.
