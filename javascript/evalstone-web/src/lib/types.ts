// Shapes from python/evalstone-api/openapi.json — keep in step with the committed schema.

export type User = { id: string; email: string; first_name: string; last_name: string; created_at: string };
export type AuthOut = { user: User; token: string };

export type Role = "member" | "admin" | "owner";
export type Organization = { id: string; name: string; website_url: string | null; created_at: string };
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

export type Run = {
  id: string;
  client_run_id: string;
  suite: string;
  pass_rate: number;
  mean_score: number;
  cost_usd: number;
  result_count: number;
  trigger: string;
  started_at: string;
  finished_at: string;
  is_baseline: boolean;
};
export type Page<T> = { items: T[]; total: number; offset: number; limit: number };

/** A frame from GET /ws/projects/{id}: {"event": "...", "project_id": "...", "at": "...", ...}. */
export type LiveEvent = { event: string; project_id?: string; at?: string } & Record<string, unknown>;
