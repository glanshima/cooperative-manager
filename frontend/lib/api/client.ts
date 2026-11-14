const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "mact_access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Thrown by apiFetch on any non-2xx response. `message` is always a
 * human-readable string (safe to render directly, e.g. via
 * `catch (e: any) { setError(e.message) }`), even when the backend's
 * `detail` was a structured object rather than a plain string (e.g.
 * self_conflict.py's 409 responses, which include an `eligible_approvers`
 * list) -- the full original `detail` value (string OR object) is also
 * kept on `.detail` for callers that want more than just the message.
 */
export class ApiError extends Error {
  detail: unknown;
  // True when fetch itself rejected, so there is no status or body to
  // inspect: the request may still have reached the server.
  transport: boolean;
  constructor(message: string, detail?: unknown, transport = false) {
    super(message);
    this.name = "ApiError";
    this.detail = detail;
    this.transport = transport;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    let message: string;
    if (typeof detail === "string" && detail) {
      message = detail;
    } else if (detail && typeof detail === "object" && typeof (detail as any).message === "string") {
      // e.g. self_conflict.py's { error, message, eligible_approvers, ... }
      message = (detail as any).message;
    } else {
      message = `Request failed with status ${res.status}`;
    }
    throw new ApiError(message, detail);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

/**
 * Shared fetch wrapper: attaches the Authorization header when a token is
 * present, sets Content-Type for JSON bodies, and never caches (all our
 * data is mutable and small-scale, so freshness matters more than speed).
 */
export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; searchParams?: Record<string, string | undefined> } = {}
): Promise<T> {
  const url = new URL(`${API_URL}${path}`);
  if (options.searchParams) {
    for (const [key, value] of Object.entries(options.searchParams)) {
      if (value !== undefined) url.searchParams.set(key, value);
    }
  }

  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
    });
  } catch {
    // A rejected fetch (offline, TLS failure, or a serverless error response
    // that CORS never exposed) has no status or body to relay. The browser
    // text "Failed to fetch" tells an officer nothing and reads as if the
    // save definitely failed, so say what can actually be checked.
    throw new ApiError(
      "Could not reach the server. Check your connection and reload the page — if you were saving, reload before retrying so you do not create a duplicate.",
      undefined,
      true
    );
  }
  return handle<T>(res);
}
