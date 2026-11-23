/** Thin fetch wrapper: adds the token, parses the API's single error format. */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

const BASE = "/api/v1";
let token: string | null = sessionStorage.getItem("blink.token");
let onUnauthorized: () => void = () => {};

export const auth = {
  get token() {
    return token;
  },
  set(t: string | null) {
    token = t;
    if (t) sessionStorage.setItem("blink.token", t);
    else sessionStorage.removeItem("blink.token");
  },
  onUnauthorized(fn: () => void) {
    onUnauthorized = fn;
  },
};

type Params = Record<string, string | number | boolean | undefined | null>;

export async function api<T>(path: string, opts: { method?: string; body?: unknown; params?: Params; form?: Record<string, string> } = {}): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(opts.params ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (opts.form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = new URLSearchParams(opts.form);
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(url, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized();
    const err = data?.error ?? {};
    throw new ApiError(res.status, err.code ?? "ERROR", err.message ?? `Request failed (${res.status})`, err.details);
  }
  return data as T;
}
