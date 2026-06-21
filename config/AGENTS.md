# Configuration Instructions

## Scope

This directory contains safe examples and defaults only.

## Rules

- Do not commit real profile files, OAuth credentials, tokens, API keys, or
  personal calendars.
- Use `.example.yaml`, `.example.json`, or documented placeholders for templates.
- Keep defaults conservative enough to run in dry or fake modes.
- Real local configuration should live outside the repository, preferably under
  `~/.config/ai-scout/`.
- Every new configurable behavior should be documented with an example.
