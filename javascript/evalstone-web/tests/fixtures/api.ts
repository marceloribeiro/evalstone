import { request, type APIRequestContext } from "@playwright/test";

/** Seed through the center API: every test gets its own user (no shared state). */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8181";

export type Seed = { email: string; password: string; token: string; api: APIRequestContext };

export async function newUser(prefix = "web"): Promise<Seed> {
  const api = await request.newContext({ baseURL: API_URL });
  const email = `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  return registerUser(api, email);
}

export async function registerUser(api: APIRequestContext, email: string): Promise<Seed> {
  const password = "playwright-pass-1";
  const res = await api.post("/auth/register", { data: { email, password, first_name: "Play", last_name: "Wright" } });
  if (!res.ok()) throw new Error(`register failed: ${res.status()} ${await res.text()}`);
  const { token } = (await res.json()) as { token: string };
  return { email, password, token, api };
}

export async function authed(seed: Seed, method: "post" | "get" | "put" | "delete", path: string, data?: unknown) {
  const res = await seed.api[method](path, { data, headers: { Authorization: `Bearer ${seed.token}` } });
  if (!res.ok()) throw new Error(`${method.toUpperCase()} ${path} → ${res.status()} ${await res.text()}`);
  return res.status() === 204 ? null : res.json();
}

export async function newOrganization(seed: Seed, name: string): Promise<{ id: string; name: string }> {
  return authed(seed, "post", "/organizations", { name });
}

export async function newProject(seed: Seed, orgId: string, name: string): Promise<{ id: string; name: string }> {
  return authed(seed, "post", `/organizations/${orgId}/projects`, { name });
}

/** Invite an existing user into the organization (the API joins them immediately). */
export async function inviteMember(seed: Seed, orgId: string, email: string, role: "member" | "admin" = "member") {
  return authed(seed, "post", `/organizations/${orgId}/invitations`, { email, role });
}

/** Mint an ingest key through the API and push a library report with it (what `evalstone run` does). */
export async function pushRun(seed: Seed, projectId: string, report: unknown) {
  const { key } = (await authed(seed, "post", `/projects/${projectId}/ingest-keys`, { name: "spec" })) as { key: string };
  const res = await seed.api.post(`/projects/${projectId}/runs`, { data: report, headers: { Authorization: `Bearer ${key}` } });
  if (res.status() !== 201) throw new Error(`push run → ${res.status()} ${await res.text()}`);
  return (await res.json()) as { id: string; client_run_id: string };
}
