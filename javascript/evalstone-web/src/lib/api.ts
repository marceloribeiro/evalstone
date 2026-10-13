export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8181";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (Array.isArray(err.detail)) {
      // pydantic validation errors: [{loc, msg, …}]
      return err.detail.map((d) => (d as { msg?: string }).msg ?? "invalid").join("; ");
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}

const TOKEN_KEY = "evalstone.token";
/** Fired on window when a request made with the stored token came back 401: the session is over. */
export const UNAUTHORIZED_EVENT = "evalstone:unauthorized";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode */
  }
}

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string | null;
  query?: Record<string, string | number | boolean | undefined>;
};

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const token = opts.token === undefined ? getToken() : opts.token;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const qs = opts.query
    ? "?" +
      Object.entries(opts.query)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join("&")
    : "";
  const res = await fetch(`${API_URL}${path}${qs}`, { method: opts.method ?? "GET", headers, body });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // an nginx 502/504 page, a proxy timeout: keep the status, show the body
    if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText || "error"}`.trim());
    throw new ApiError(res.status, "the API returned something that is not JSON");
  }
  if (!res.ok) {
    if (res.status === 401 && opts.token === undefined && token) {
      // the persisted session is no longer accepted (expired / revoked): drop it once, tell the app
      setToken(null);
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, detail ?? data);
  }
  return data as T;
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

/** ws(s)://… for a path on the API host (the browser opens the socket on the API directly). */
export function wsUrl(path: string): string {
  const u = new URL(API_URL);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = path;
  u.search = "";
  return u.toString();
}
