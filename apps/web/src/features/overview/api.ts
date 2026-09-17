import { apiFetch } from "@/services/apiClient";
import type {
  AuditIntegrityCheckRecord,
  Decision,
  FairnessEvaluation,
  HealthStatus,
  MonitoringAlert,
  MonitoringMetrics,
} from "@/types/api";

export function fetchMetrics(tenantId: string): Promise<MonitoringMetrics> {
  return apiFetch<{ metrics: MonitoringMetrics }>("/monitoring/metrics", { tenantId }).then((r) => r.metrics);
}

export function fetchRecentDecisions(tenantId: string): Promise<Decision[]> {
  return apiFetch<{ decisions: Decision[] }>("/decisions?limit=5", { tenantId }).then((r) => r.decisions);
}

export function fetchRecentAlerts(tenantId: string): Promise<MonitoringAlert[]> {
  return apiFetch<{ alerts: MonitoringAlert[] }>("/monitoring/alerts", { tenantId }).then((r) => r.alerts);
}

export function fetchIntegrityStatus(tenantId: string): Promise<AuditIntegrityCheckRecord | null> {
  return apiFetch<{ latest_check: AuditIntegrityCheckRecord | null }>("/audit/integrity-status", {
    tenantId,
  }).then((r) => r.latest_check);
}

export function fetchApiHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}

export function fetchFairnessReports(tenantId: string): Promise<FairnessEvaluation[]> {
  return apiFetch<{ reports: FairnessEvaluation[] }>("/fairness/reports", { tenantId }).then((r) => r.reports);
}
