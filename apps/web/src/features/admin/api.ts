import { apiFetch } from "@/services/apiClient";
import type { Tenant } from "@/types/api";

// Migrated to OIDC auth; also the only admin-shaped endpoint that exists
// today (see app/api/v1/tenants.py) -- it returns only the caller's own
// tenant, since no role in this application is a cross-tenant platform
// administrator.
export function fetchOwnTenant(accessToken: string | undefined): Promise<Tenant> {
  return apiFetch<{ tenants: Tenant[] }>("/tenants", { accessToken }).then((r) => r.tenants[0]);
}
