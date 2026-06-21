# LangGraph Instructions

## Scope

This directory owns graph construction, graph state, routing, retries, and run
lifecycle orchestration.

## Rules

- Keep graph nodes small and named after their responsibility.
- Do not put service-specific API code in graph nodes; call MCP-facing services.
- Make retry and fallback behavior explicit in graph edges or node results.
- Avoid unbounded loops. Any loop must have a clear counter, stop condition, and
  logged reason for termination.
- Preserve enough state to resume or audit a run.

## Expected Nodes

- Load profile and policy.
- Load memory.
- Discover resources.
- Inspect resources in parallel where practical.
- Deduplicate.
- Rank.
- Build learning plan.
- Read calendar availability.
- Write calendar events.
- Write memory and reports.
- Audit the final run.
