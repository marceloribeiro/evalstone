// Shapes from python/evalstone-api/openapi.json — keep in step with the committed schema.

export type User = { id: string; email: string; first_name: string; last_name: string; created_at: string };
export type AuthOut = { user: User; token: string };

export type Role = "member" | "admin" | "owner";
export type Organization = { id: string; name: string; website_url: string | null; created_at: string };
/** `GET /organizations/{id}`: the organization plus the caller's role in it. */
export type OrganizationDetail = Organization & { role: Role };
export type Member = { id: string; role: Role; user: User; created_at: string };

export type Project = {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string;
  created_at: string;
};

export type IngestKey = {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};
export type IngestKeyCreated = IngestKey & { key: string };

export type CheckSummary = {
  key: string;
  n: number;
  passed: number;
  errors: number;
  skipped: number;
  pass_rate: number;
  mean_score: number;
  cost_usd: number;
};
export type RunSummary = {
  samples: number;
  checks: number;
  results: number;
  passed: number;
  errors: number;
  skipped: number;
  pass_rate: number;
  mean_score: number;
  error_rate: number;
  cost_usd: number;
  duration_ms: number;
  per_check: CheckSummary[];
  per_tag: Record<string, number>;
};
/** `RunOut` — one stored library report. */
export type Run = {
  id: string;
  project_id: string;
  client_run_id: string;
  suite: string;
  dataset_name: string;
  dataset_hash: string;
  dataset_version_id: string | null;
  target: Record<string, unknown>;
  check_keys: string[];
  git_sha: string | null;
  trigger: string;
  baseline_run_id: string | null;
  client_baseline_run_id: string | null;
  started_at: string;
  finished_at: string;
  summary: RunSummary;
  pass_rate: number;
  mean_score: number;
  error_rate: number;
  cost_usd: number;
  duration_ms: number;
  result_count: number;
  gate_passed: boolean | null;
  gate_lines: string[];
  is_baseline: boolean;
  created_by_user_id: string | null;
  created_at: string;
};
/** `GET /projects/{id}/runs/suites` — distinct suites with counts and baselines. */
export type Suite = { suite: string; runs: number; last_started_at: string; baseline_run_id: string | null };
/** `ResultOut` — one (sample, check) row of a run. */
export type RunResult = {
  id: string;
  sample_key: string;
  check_key: string;
  tags: string[];
  input: unknown;
  expected: unknown;
  output: { value?: unknown; model?: string | null; latency_ms?: number; cost_usd?: number; error?: string | null } & Record<string, unknown>;
  score: number;
  passed: boolean;
  reason: string;
  cost_usd: number;
  latency_ms: number;
  error: string | null;
  skipped: boolean;
};
/** The library's `Score` as it appears inside a comparison flip. */
export type Score = { value: number; passed: boolean; reason: string; error: string | null; skipped: boolean };
export type Flip = { sample_id: string; check_key: string; before: Score; after: Score };
/** `GET /runs/{a}/compare/{b}`: run B relative to run A (the library's `compare()`). */
export type Comparison = {
  a: string;
  b: string;
  same_dataset: boolean;
  pass_rate_delta: number;
  mean_score_delta: number;
  cost_delta: number;
  regressions: Flip[];
  improvements: Flip[];
  only_in_a: string[];
  only_in_b: string[];
};
export type Page<T> = { items: T[]; total: number; offset: number; limit: number };

/** `DatasetOut` — a named, tagged dataset; its content lives in immutable versions. */
export type Dataset = { id: string; project_id: string; name: string; description: string; tags: string[]; created_at: string };
/** `VersionOut` — one immutable, content-hashed snapshot of a dataset (hash == the library's). */
export type DatasetVersion = {
  id: string;
  dataset_id: string;
  version: number;
  content_hash: string;
  sample_count: number;
  note: string;
  created_by_user_id: string | null;
  created_at: string;
};
/** `SampleOut` — a content-addressed sample as the library sees it. */
export type Sample = {
  id: string;
  sample_key: string;
  content_hash: string;
  input: unknown;
  expected: unknown;
  metadata: Record<string, unknown>;
  tags: string[];
  source: string;
};

/** A frame from GET /ws/projects/{id}: {"event": "...", "project_id": "...", "at": "...", ...}. */
export type LiveEvent = { event: string; project_id?: string; at?: string } & Record<string, unknown>;
