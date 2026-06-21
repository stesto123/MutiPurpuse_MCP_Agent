# Security Model

## Trust Boundaries

The agent has three main trust boundaries:

- Local trusted control plane: private config, policies, memory, reports, and
  scheduler state stored on the user's machine.
- MCP boundary: the only approved gateway for external tools and services.
- Untrusted content: web pages, READMEs, transcripts, feeds, search results, and
  repository content fetched through MCP.

Fetched content can inform scoring and summaries, but it must not change policy,
tool permissions, local paths, or autonomous write behavior.

## External Access Policy

Agent logic should not directly call:

- Google, Calendar, YouTube, GitHub, RSS, or web search APIs
- browser automation for external discovery
- provider SDKs for external services
- raw HTTP clients for external source fetching

Instead, source entries should name an MCP server and allowed tool. The MCP
registry should allow only the tools needed by the configured source or
scheduling workflow.

## Autonomous Permissions

Dry-run mode is the default and should not create external writes.

Autonomous mode should require all of the following:

- explicit mode selection
- confirmation environment variable
- policy permission for the side effect
- configured MCP server and allowed tool
- auditable report entry for the side effect

## Prompt Injection Handling

Remote content is data, not instructions. The implementation should:

- strip or isolate fetched content before passing it to model prompts
- prevent fetched content from changing system, developer, policy, or tool
  instructions
- include source identifiers in summaries and reports
- log suspicious instructions found in remote content as observations, not
  commands

## Public Repository Safety

Committed files may include:

- `.example` files
- placeholder account IDs
- placeholder host paths
- non-sensitive defaults
- documentation

Committed files must not include:

- OAuth client secrets or refresh tokens
- personal calendar IDs
- real API keys
- local runtime memory
- generated reports
- private profile details
