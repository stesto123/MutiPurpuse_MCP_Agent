# Architecture Overview

## Current Status

This repository currently contains the public-safe project skeleton, initial
Python package and CLI, example configuration, local infrastructure templates,
and documentation for the AI Scout agent.

The committed templates define the integration contract the implementation
should follow.

## Design Principles

- Local-first: runtime memory, run reports, and private configuration live on
  the user's machine.
- MCP-only external access: Google, GitHub, YouTube, RSS, web search, browser
  automation, and similar services must be reached through MCP servers.
- Side effects at boundaries: writes happen only through the MCP layer, memory
  layer, report writer, or scheduler boundary.
- Auditable autonomy: every external read, local write, score, scheduling
  decision, and calendar write should be traceable in a run report.
- Public-repo safety: committed files contain examples and placeholders only.

## Expected Runtime Flow

1. Load profile, policy, source catalog, and MCP server registry from local
   configuration.
2. Discover candidate resources by calling allowed MCP tools from configured
   source entries.
3. Inspect candidates through specialist agents, treating fetched content as
   untrusted input.
4. Deduplicate candidates against local memory and the current run.
5. Score candidates with explicit policy weights and thresholds.
6. Plan learning sessions using scheduling policy and calendar availability.
7. In dry-run mode (`dry_run`), write reports without external writes.
8. In autonomous mode, persist memory and create calendar events through MCP
   tools when policy allows it.

When no enabled MCP servers are present, the CLI uses a deterministic local
MCP-shaped gateway so the graph can be tested without credentials. Private
configs can enable real stdio MCP servers; the sync runtime adapter still routes
calls through the MCP registry and never through provider SDKs directly.

## Directory Roles

- `src/ai_scout/graph`: LangGraph orchestration and state transitions.
- `src/ai_scout/agents`: specialist agents with narrow responsibilities.
- `src/ai_scout/mcp`: MCP sessions, tool registry, and gateway enforcement.
- `src/ai_scout/memory`: local persistent state, deduplication, idempotency.
- `src/ai_scout/policies`: scoring, scheduling, permissions, and budgets.
- `src/ai_scout/reporting`: Markdown and JSON run reports.
- `src/ai_scout/scheduling`: calendar planning logic without direct calendar
  API calls.
- `config`: committed examples only.
- `infra`: local Docker Compose, image, launchd, and run templates.
- `data`: local runtime data only; generated contents should stay out of Git.

## State Boundaries

The agent should pass structured state between graph nodes. Avoid handing
free-form strings between nodes when a typed model can represent the same
decision. Candidate resources, tool calls, scoring decisions, planned sessions,
and side effects should have stable identifiers so reports and rollback steps
can reference them.

## Side Effect Boundaries

The implementation should centralize side effects behind narrow interfaces:

- MCP client: external reads and external writes.
- Memory store: local deduplication and idempotency records.
- Report writer: local Markdown and JSON reports.
- Scheduler: planning decisions and MCP calendar write requests.

Agent logic should not import provider SDKs, call HTTP APIs directly, or write
to external services outside these boundaries.
