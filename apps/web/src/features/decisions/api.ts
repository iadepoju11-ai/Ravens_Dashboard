import { apiFetch } from "@/services/apiClient";
import type { Decision, DecisionOutcome, Explanation } from "@/types/api";

export interface DecisionFilters {
  outcome?: DecisionOutcome;
  modelVersionId?: string;
  dateFrom?: string;
  dateTo?: string;
}

export function fetchDecisions(accessToken: string | undefined, filters: DecisionFilters): Promise<Decision[]> {
  const params = new URLSearchParams();
  if (filters.outcome) params.set("outcome", filters.outcome);
  if (filters.modelVersionId) params.set("model_version_id", filters.modelVersionId);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  params.set("limit", "50");

  return apiFetch<{ decisions: Decision[] }>(`/decisions?${params.toString()}`, { accessToken }).then(
    (r) => r.decisions,
  );
}

export function fetchDecision(
  accessToken: string | undefined,
  decisionId: string,
): Promise<{ decision: Decision; explanation: Explanation | null }> {
  return apiFetch(`/decisions/${decisionId}`, { accessToken });
}
