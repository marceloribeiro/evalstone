# Changelog — evalstone (the library)

All notable changes to `python/evalstone`. Semantic versioning; tags `lib-vX.Y.Z`.

## 0.1.0 — unreleased

The first usable release: the hero path from `evalstone.yaml` to a gated run.

- **Core**: `Sample` / `Dataset` (JSONL, content-hashed versions, deterministic
  filter / sample / split), `Output`, `Score` (an error is never a pass), the
  `Check` protocol, `@check`, the registry.
- **Deterministic checks**: `exact`, `contains`, `regex`, `json_schema`
  (JSON Schema or pydantic), `numeric_tolerance`, `length`, `python`.
- **Targets**: `callable`, `http`, `recorded`, `prompt`.
- **Suite / Run / Gate**: per-check and per-tag summaries, dataset hash + git SHA
  provenance, baseline regression gate, error-rate gate (default 0), JSON
  report, `compare`.
- **CLI**: `init`, `run`, `gate`, `compare`, `show`, `list`.
- **Providers**: OpenAI-compatible (OpenAI, OpenRouter, Ollama, vLLM),
  Anthropic (official SDK, `evalstone[anthropic]`), Gemini; pricing table with
  overrides; unknown models reported as unpriced.
- **LLM-as-judge**: rubric → small scale → JSON verdict, reference excluded
  unless asked, judge version hash, content-keyed cache.
- **RAG** (faithfulness, context relevance, answer relevance), **safety**
  (refusal, no_pii, forbidden), **pairwise** comparison (both orders),
  **trajectory** (tool_called, tool_order, max_steps, no_repeated_calls, finished).
- **Sample**: `samples/rag-bot` — a no-LLM retrieval bot with a gated suite.
