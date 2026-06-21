# Test Instructions

## Scope

This directory contains unit, integration, and fixture tests.

## Rules

- Tests must run without real personal accounts or real secrets.
- Use fake MCP clients/servers for external capabilities.
- Unit-test pure scoring, deduplication, policy, scheduling, and state logic.
- Integration tests may exercise the graph with fake MCP tools.
- Avoid tests that depend on live internet, live Google Calendar, or current
  GitHub/YouTube state unless explicitly marked and skipped by default.
- Keep fixtures anonymized and free of personal data.
