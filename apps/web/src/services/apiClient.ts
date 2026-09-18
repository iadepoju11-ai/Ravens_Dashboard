const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:5000/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions {
  // Sent for endpoints already migrated to OIDC auth (see
  // docs/architecture/oidc-rbac.md) -- tenant identity there comes from
  // this token, verified server-side, never from tenantId below.
  accessToken?: string;
  // Still required by the handful of endpoints not yet migrated
  // (monitoring, datasets) -- harmless to send alongside accessToken,
  // since a migrated endpoint ignores this header entirely.
  tenantId?: string;
  method?: string;
  body?: unknown;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }
  if (options.tenantId) {
    headers["X-Tenant-Id"] = options.tenantId;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // A non-JSON body (a 204, or an upstream proxy error page) — leave
    // payload as null rather than throw on parsing itself.
  }

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in payload
        ? String((payload as { error: unknown }).error)
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }

  return payload as T;
}
