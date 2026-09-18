import { apiFetch } from "@/services/apiClient";
import type {
  AuditIntegrityCheckRecord,
  Decision,
  FairnessEvaluation,
  HealthStatus,
  MonitoringAlert,
  MonitoringMetrics,
} from "@/types/api";

// tenantId is still needed for the two endpoints below not yet migrated
// to OIDC auth (monitoring); accessToken is what the other four actually
// authorize against. Every call takes both so call sites don't need to
// know which endpoints are migrated -- see docs/architecture/oidc-rbac.md.
export interface AuthedRequest {
  accessToken: string | undefined;
  tenantId: string | undefined;
}

export function fetchMetrics({ accessToken, tenantId }: AuthedRequest): Promise<MonitoringMetrics> {
  return apiFetch<{ metrics: MonitoringMetrics }>("/monitoring/metrics", { accessToken, tenantId }).then(
    (r) => r.metrics,
  );
}

export function fetchRecentDecisions({ accessToken, tenantId }: AuthedRequest): Promise<Decision[]> {
  return apiFetch<{ decisions: Decision[] }>("/decisions?limit=5", { accessToken, tenantId }).then(
    (r) => r.decisions,
  );
}

export function fetchRecentAlerts({ accessToken, tenantId }: AuthedRequest): Promise<MonitoringAlert[]> {
  return apiFetch<{ alerts: MonitoringAlert[] }>("/monitoring/alerts", { accessToken, tenantId }).then(
    (r) => r.alerts,
  );
}

export function fetchIntegrityStatus({
  accessToken,
  tenantId,
}: AuthedRequest): Promise<AuditIntegrityCheckRecord | null> {
  return apiFetch<{ latest_check: AuditIntegrityCheckRecord | null }>("/audit/integrity-status", {
    accessToken,
    tenantId,
  }).then((r) => r.latest_check);
}

export function fetchApiHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}

export function fetchFairnessReports({ accessToken, tenantId }: AuthedRequest): Promise<FairnessEvaluation[]> {
  return apiFetch<{ reports: FairnessEvaluation[] }>("/fairness/reports", { accessToken, tenantId }).then(
    (r) => r.reports,
  );
}
