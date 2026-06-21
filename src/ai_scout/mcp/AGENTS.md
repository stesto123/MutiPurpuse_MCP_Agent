# MCP Layer Instructions

## Scope

This directory is the only place where the application should connect to MCP
servers or invoke MCP tools.

## Rules

- External capabilities must be represented as MCP servers/tools.
- Do not bypass MCP with direct HTTP clients, service SDKs, shell commands, or
  browser automation from application logic.
- Keep MCP server configuration data-driven.
- Use explicit tool allowlists per server where possible.
- Add timeouts, retries, and clear error messages around tool calls.
- Redact secrets from logs and exceptions.
- Validate tool outputs before passing them to the graph.

## Testing

- Provide fake or in-memory MCP clients for tests.
- Tests must not require real Google, GitHub, YouTube, RSS, or web-search
  credentials.
