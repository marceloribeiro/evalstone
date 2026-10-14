// Shapes from python/evalstone-api/openapi.json — keep in step with the committed schema.

export type User = { id: string; email: string; first_name: string; last_name: string; created_at: string };
export type AuthOut = { user: User; token: string };

export type Role = "member" | "admin" | "owner";
export type Organization = { id: string; name: string; website_url: string | null; created_at: string };
/** `GET /organizations/{id}`: the organization plus the caller's role in it. */
export type OrganizationDetail = Organization & { role: Role };
export type Member = { id: string; role: Role; user: User; created_at: string };
/** `InvitationOut` — a pending (or accepted) invitation; an existing user joins at once, a new one on registration. */
export type Invitation = { id: string; email: string; role: Role; created_at: string; accepted_at: string | null; status: "pending" | "accepted" };

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

export type QueueKind = "grade" | "compare" | "verify";
/** `QueueOut` — a labeling queue materialised from a run (grade), two runs (compare) or a dataset version (verify). */
export type LabelQueue = {
  id: string;
  project_id: string;
  name: string;
  kind: QueueKind;
  instructions: string;
  check_key: string;
  scale: number;
  source: Record<string, unknown>;
  status: "open" | "closed";
  due_at: string | null;
  task_count: number;
  created_by_user_id: string | null;
  created_at: string;
};
export type QueueProgress = { total: number; pending: number; claimed: number; done: number; skipped: number };
export type MachineVerdict = { score: number; passed: boolean; reason: string };
export type OutputPayload = { value?: unknown; model?: string | null; error?: string | null } & Record<string, unknown>;
/** `TaskOut.payload` per kind (see services/label_queues._grade_items / _compare_items / _verify_items). */
export type GradePayload = { input: unknown; expected: unknown; output: OutputPayload; run_id: string; result_id: string; check_key: string; machine: MachineVerdict };
export type ComparePayload = { input: unknown; expected: unknown; a: { run_id: string; output: OutputPayload; hash: string }; b: { run_id: string; output: OutputPayload; hash: string } };
export type VerifyPayload = { input: unknown; expected: unknown; sample_id: string; dataset_version_id: string };
export type LabelTask = {
  id: string;
  queue_id: string;
  position: number;
  sample_key: string;
  output_hash: string;
  payload: (GradePayload | ComparePayload | VerifyPayload) & { skip_reason?: string };
  status: "pending" | "done" | "skipped";
  assignee_user_id: string | null;
  claimed_at: string | null;
  done_at: string | null;
  label_id: string | null;
};

export type Adapter = "openai" | "anthropic" | "gemini";
/** `ProviderOut` — an organization's model provider; the key never comes back (only `has_api_key` + `key_last4`). */
export type Provider = {
  id: string;
  name: string;
  adapter: Adapter;
  base_url: string | null;
  headers: Record<string, string>;
  prices: Record<string, number[]>;
  timeout_s: number;
  max_tokens_param: string | null;
  has_api_key: boolean;
  key_last4: string | null;
  verified_ok: boolean | null;
  last_verified_at: string | null;
  last_error: string | null;
  created_at: string;
};
export type ProviderTest = { ok: boolean; model: string; latency_ms: number | null; input_tokens: number; output_tokens: number; cost_usd: number | null; error: string | null };
/** `JudgeSettingsOut` — which `<provider>/<model>` judges run on, per check or by default. */
export type JudgeSettings = { project_id: string; default_model: string | null; overrides: Record<string, string> };
/** `JudgeOut` — a (check, judge version) seen in stored results. */
export type JudgeSeen = { check_key: string; judge_version: string; model: string | null; results: number; runs: number; first_seen: string; last_seen: string };
/** `CalibrationOut` — judge verdicts vs human labels for one check + judge version. */
export type Calibration = {
  id: string;
  project_id: string;
  check_key: string;
  judge_version: string;
  label_check: string;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  n: number;
  agreement: number | null;
  kappa: number | null;
  mean_abs_error: number | null;
  confusion: { tp?: number; fp?: number; fn?: number; tn?: number };
  model: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_by_user_id: string | null;
  created_at: string;
};

/** `CheckOut` — an organization catalog check (type + params, versioned). */
export type CatalogCheck = {
  id: string;
  organization_id: string;
  key: string;
  type: string;
  kind: string;
  params: Record<string, unknown>;
  description: string;
  current_version: number;
  created_at: string;
  updated_at: string;
};
export type AlertPolicy = { metric: "pass_rate" | "mean_score"; threshold: number; window_minutes: number; min_n: number };
/** `MonitorOut` — sampled production traces scored by catalog checks on the beat, with an alert policy. */
export type Monitor = {
  id: string;
  project_id: string;
  name: string;
  check_keys: string[];
  sample_rate: number;
  alert_policy: AlertPolicy;
  webhook_url: string | null;
  status: "active" | "paused";
  last_scored_at: string | null;
  last_error: string | null;
  created_at: string;
};
export type MonitorWindow = { n: number; pass_rate: number | null; mean_score: number | null; window_minutes: number };
/** `AlertOut` — a policy breach, open until the metric is back at/above the threshold. */
export type Alert = {
  id: string;
  monitor_id: string;
  metric: string;
  value: number;
  threshold: number;
  n: number;
  window_minutes: number;
  opened_at: string;
  resolved_at: string | null;
  notified_at: string | null;
  notify_error: string | null;
};
/** `TraceOut` — one production interaction pushed by the app. */
export type Trace = {
  id: string;
  client_id: string;
  input: unknown;
  output: unknown;
  output_hash: string;
  metadata: Record<string, unknown>;
  tags: string[];
  model: string | null;
  latency_ms: number | null;
  cost_usd: number | null;
  occurred_at: string;
  flagged: boolean;
  sample_bucket: number;
};

/** A frame from GET /ws/projects/{id}: {"event": "...", "project_id": "...", "at": "...", ...}. */
export type LiveEvent = { event: string; project_id?: string; at?: string } & Record<string, unknown>;
