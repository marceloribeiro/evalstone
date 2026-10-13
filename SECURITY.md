# Security policy

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Use GitHub's
private vulnerability reporting on this repository
(**Security → Report a vulnerability**). You will get an acknowledgement
within 72 hours and a fix or mitigation plan as soon as the issue is confirmed.

## Scope

- `python/evalstone` — the library, CLI and MCP server
- `python/evalstone-api` — the self-hostable center API
- `javascript/evalstone-web` — the center web app
- `javascript/evalstone-site` — the marketing + docs site

## Principles

- Provider API keys are read from the environment and never persisted.
- The center stores evaluation inputs and outputs only where the operator
  explicitly configured it to.
