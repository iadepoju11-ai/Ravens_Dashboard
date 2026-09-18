import { apiFetch } from "@/services/apiClient";
import type { Dataset, DatasetVersion } from "@/types/api";

// Not yet migrated to OIDC auth (see docs/architecture/oidc-rbac.md) --
// tenantId (from the header) is what authorizes these calls, not
// accessToken. Still send accessToken too; the backend ignores it here.
export function fetchDatasets(tenantId: string | undefined): Promise<Dataset[]> {
  return apiFetch<{ datasets: Dataset[] }>("/datasets", { tenantId }).then((r) => r.datasets);
}

export function registerDataset(
  tenantId: string | undefined,
  body: { name: string; version: string; uri: string },
): Promise<{ dataset: Dataset; version: DatasetVersion }> {
  return apiFetch("/datasets", { tenantId, method: "POST", body });
}
