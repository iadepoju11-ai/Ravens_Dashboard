import { apiFetch } from "@/services/apiClient";
import type { FairnessEvaluation } from "@/types/api";

export function fetchFairnessReports(accessToken: string | undefined): Promise<FairnessEvaluation[]> {
  return apiFetch<{ reports: FairnessEvaluation[] }>("/fairness/reports", { accessToken }).then((r) => r.reports);
}
