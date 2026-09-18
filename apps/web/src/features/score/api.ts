import { apiFetch } from "@/services/apiClient";
import type { Decision, Explanation } from "@/types/api";

export interface ScoreResponse {
  decision: Decision;
  explanation: Explanation | null;
}

export function scoreApplication(
  accessToken: string | undefined,
  body: {
    application_reference: string;
    features: Record<string, number | string | boolean>;
    model_version_id?: string;
    request_id?: string;
  },
): Promise<ScoreResponse> {
  return apiFetch<ScoreResponse>("/score", { accessToken, method: "POST", body });
}
