# Infrastructure Instructions

## Scope

This directory contains local runtime infrastructure: Docker Compose, Docker
files, launchd units, and operational scripts.

## Rules

- Target local execution first.
- Do not add cloud infrastructure unless explicitly requested.
- Do not bake secrets into images, compose files, launchd files, or scripts.
- Prefer mounted secret files or host secret stores over environment variables
  for long-lived credentials.
- Keep runtime volumes explicit and ignored by Git.
- Make services restartable and observable with logs and health checks when
  practical.

## Runtime Goal

The project should support:

- fast local development through `uv`;
- production-like local execution through Docker Compose;
- scheduled local execution through launchd or an equivalent scheduler.
