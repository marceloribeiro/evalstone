# Changelog — evalstone (the library)

All notable changes to `python/evalstone`. Semantic versioning; tags `lib-vX.Y.Z`.

## 0.2.1 — 2026-10-14

Attach fixes found by the docs audit.

- `comparison.pairwise` built its check version (and so its cache key) from
  `--judge-model` or the check's own `model:`, ignoring the attached project's
  per-check override — the call itself already honoured it. Both now resolve through
  the same precedence (`--judge-model` > center override > `model:` > default), so a
  verdict cached under the override is found again and a changed override invalidates
  the cache.
- Docstrings and this changelog no longer claim prompt targets are proxied when
  attached; they never were (`providers:` + env keys serve the system under test).
- Known limitation, documented: when attached, `--judge-model some-typo/model` is
  not validated up front — the center only rejects the provider at the first judge
  call, which surfaces as an errored score. Standalone runs still fail fast.

## 0.2.0 — 2026-10-14

Attach a project to a center.

- `center:` in `evalstone.yaml` (`url`, `project`, `api_key_env` — an `es_…` ingest key)
  routes judge calls through the center's model proxy, so no judge key lives on the
  machine running the suite; the project's judge settings pick the model (per-check
  overrides, then the default), `--judge-model` still wins.
- Judge verdicts are cached in the center (`CenterCache`); a center hiccup is a cache
  miss, never a failed run.
- `human` checks of an attached project look labels up in the center (`labels: center`,
  the default when attached; a file path still works).
- `evalstone run` pushes its report to the center (`push_runs: false` to opt out); a
  failed push warns and leaves the exit code alone.
- Prompt targets (the system under test) always use the local `providers:` + env keys,
  even when attached — the center proxy is for judges only. The MCP server honours the
  attach too.

## 0.1.1 — 2026-10-13

Judge switching and cost honesty.

- **Named providers**: a `providers:` entry may name any adapter (`adapter:
  openai | anthropic | gemini`), so `openrouter:`, `ollama:` and `openai:` can
  coexist and a judge model reads `openrouter/anthropic/claude-haiku-5-5`.
  Unknown provider names and adapters are reported with the known ones. A
  named entry never falls back to the adapter's default key variable (one
  vendor's key is never sent to another); a 401/403 without a key says so.
- **`--judge-model provider/model`** on `evalstone run` and `gate` overrides
  every judge's and pairwise comparison's model for that run — never the
  target under test (`Context.judge_model`; `Config.context(judge_model=…)`).
  Validated before the run starts; a typo exits 2.
- **`short_circuit: true`** on a suite skips the judge checks on a sample that
  a contract check (deterministic, safety, trajectory — not a human label,
  which is a quality verdict the judge should still be compared against)
  already failed. The skipped result is a failure, not an error
  (`Score.skipped`, `RunSummary.skipped`, `CheckSummary.skipped`), so no paid
  call is spent on an output that already failed and the error-rate gate is
  not tripped. Off by default. Turning it on changes pass rates (a skipped
  judge counts as a failure), so re-take your baseline when you enable it.
- **Cheap-first ordering** now includes safety rules and human labels, not only
  deterministic and trajectory checks.
- **Gate**: with `max_cost_usd` set, a `WARN` line counts results from models
  outside the price table (they count as $0). Gemini models priced from the
  official table (2026-10-09); OpenAI models are set under `prices:`.

## 0.1.0 — 2026-10-13

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
- **MCP server** (`evalstone mcp`, extra `evalstone[mcp]`): `list_suites`,
  `run_suite`, `judge_output`, `record_sample`, `compare_runs`, `get_run` over
  stdio; calls run one at a time, stray stdout goes to stderr, one provider
  registry and judge cache per session, report paths relative to the config.
- **pytest plugin** (entry point `pytest11`): `@suite("name")`, fixtures
  `evalstone_run` / `evalstone_gate` / `evalstone_config`, options
  `--evalstone-config` and `--evalstone-baseline` (a report or a directory of
  them); one report per suite (`evalstone-report.<suite>.json`); a suite without
  a gate fails the gated forms; the package imports lazily so the plugin costs
  nothing in unrelated test sessions.
- **GitHub Action** (`action/`): run a suite on a pull request, job summary,
  in-place PR comment (`evalstone show --markdown`), fail on the gate; inputs
  bound through the environment; `report` output is an absolute path.
- **Human labels**: `evalstone label <report>` grades outputs in the terminal
  (pass/fail or a 1..N scale, resumable, keyed by sample id + output hash); the
  `human` check scores from the labels file and errors on unlabelled outputs.
- **Reports**: `Run.markdown()`, `Run.failure_lines()`, results carry the
  sample's input and expected value.
- **Loading**: project modules are reused across runs in one process unless a
  file changed or the registry was cleared, so test patches reach suites.
