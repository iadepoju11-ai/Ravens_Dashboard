import { apiFetch } from "@/services/apiClient";
import type { Tenant } from "@/types/api";

// Not yet migrated to OIDC auth; also the only admin-shaped endpoint that
// exists today (see app/api/v1/tenants.py) -- it returns only the
// caller's own tenant until a platform-administrator role exists there.
export function fetchOwnTenant(tenantId: string | undefined): Promise<Tenant> {
  return apiFetch<{ tenants: Tenant[] }>("/tenants", { tenantId }).then((r) => r.tenants[0]);
}
