import { apiFetch } from "@/services/apiClient";
import type {
  AuditIntegrityCheckRecord,
  Decision,
  FairnessEvaluation,
  HealthStatus,
  MonitoringAlert,
  MonitoringMetrics,
} from "@/types/api";

export function fetchMetrics(accessToken: string | undefined): Promise<MonitoringMetrics> {
  return apiFetch<{ metrics: MonitoringMetrics }>("/monitoring/metrics", { accessToken }).then((r) => r.metrics);
}

export function fetchRecentDecisions(accessToken: string | undefined): Promise<Decision[]> {
  return apiFetch<{ decisions: Decision[] }>("/decisions?limit=5", { accessToken }).then((r) => r.decisions);
}

export function fetchRecentAlerts(accessToken: string | undefined): Promise<MonitoringAlert[]> {
  return apiFetch<{ alerts: MonitoringAlert[] }>("/monitoring/alerts", { accessToken }).then((r) => r.alerts);
}

export function fetchIntegrityStatus(accessToken: string | undefined): Promise<AuditIntegrityCheckRecord | null> {
  return apiFetch<{ latest_check: AuditIntegrityCheckRecord | null }>("/audit/integrity-status", {
    accessToken,
  }).then((r) => r.latest_check);
}

export function fetchApiHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}

export function fetchFairnessReports(accessToken: string | undefined): Promise<FairnessEvaluation[]> {
  return apiFetch<{ reports: FairnessEvaluation[] }>("/fairness/reports", { accessToken }).then((r) => r.reports);
}
