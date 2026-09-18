import { apiFetch } from "@/services/apiClient";
import type { Dataset, DatasetVersion } from "@/types/api";

// Migrated to OIDC auth (see docs/architecture/oidc-rbac.md) --
// accessToken is what authorizes these calls now, not the X-Tenant-Id
// header a tenantId-only call used to rely on.
export function fetchDatasets(accessToken: string | undefined): Promise<Dataset[]> {
  return apiFetch<{ datasets: Dataset[] }>("/datasets", { accessToken }).then((r) => r.datasets);
}

export function registerDataset(
  accessToken: string | undefined,
  body: { name: string; version: string; uri: string },
): Promise<{ dataset: Dataset; version: DatasetVersion }> {
  return apiFetch("/datasets", { accessToken, method: "POST", body });
}
