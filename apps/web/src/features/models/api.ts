import { apiFetch } from "@/services/apiClient";
import type { Model, ModelDeployment, ModelVersion } from "@/types/api";

export function fetchModels(accessToken: string | undefined): Promise<Model[]> {
  return apiFetch<{ models: Model[] }>("/models", { accessToken }).then((r) => r.models);
}

export function registerModelVersion(
  accessToken: string | undefined,
  body: { name: string; version: string; artifact_uri: string },
): Promise<{ model: Model; model_version: ModelVersion }> {
  return apiFetch("/models", { accessToken, method: "POST", body });
}

export function approveModelVersion(
  accessToken: string | undefined,
  modelVersionId: string,
): Promise<{ model_version: ModelVersion }> {
  return apiFetch(`/models/${modelVersionId}/approve`, { accessToken, method: "POST" });
}

export function deployModelVersion(
  accessToken: string | undefined,
  modelVersionId: string,
): Promise<{ model_version: ModelVersion; deployment: ModelDeployment }> {
  return apiFetch(`/models/${modelVersionId}/deploy`, { accessToken, method: "POST" });
}
