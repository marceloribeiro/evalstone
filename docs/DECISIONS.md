# Decisions

Short architecture decision records. Newest last.

## ADR-001 — PostgreSQL only; the center API is the sole database owner (2026-10-12)

The library owns no database (no SQLite). Runs print and write a JSON report;
persistence happens through the center API, which is the only process that
touches PostgreSQL. One storage engine, one migration tool, one place to
reason about data.

## ADR-002 — Own thin judge adapters, no litellm (2026-10-12)

OpenAI-compatible (covers OpenAI, OpenRouter, Ollama, vLLM), Anthropic and
Gemini adapters translate one canonical message shape. Keeps the library light.

## ADR-003 — Docs are a course first (2026-10-12)

The site teaches what evals are and why before it documents the API. Every
concept page: why → the pitfall → the API.

## ADR-004 — Site ships first (2026-10-12)

The domain was registered before the library existed. The site and the
learning center go live first; the Evalstone pages state the status honestly.
