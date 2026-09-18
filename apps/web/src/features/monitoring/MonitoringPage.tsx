import { AsyncSection } from "@/components/AsyncSection";
import { KpiCard } from "@/components/KpiCard";
import { fetchMetrics, fetchRecentAlerts } from "@/features/overview/api";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";

// Migrated to OIDC auth (monitoring:read -- see docs/architecture/oidc-rbac.md).
// Reuses the Overview page's fetchers.
export function MonitoringPage() {
  const { accessToken } = useIdentity();

  const metricsState = useApiResource(() => fetchMetrics(accessToken), [accessToken]);
  const alertsState = useApiResource(() => fetchRecentAlerts(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });

  return (
    <div className="monitoring-page">
      <div className="page-header">
        <h1>Monitoring</h1>
      </div>

      <section className="kpi-grid" aria-label="Key metrics">
        <AsyncSection state={metricsState}>
          {(metrics) => (
            <>
              <KpiCard label="Total decisions" value={metrics.decision_count} />
              <KpiCard
                label="Approval rate"
                value={metrics.approval_rate === null ? "—" : `${Math.round(metrics.approval_rate * 100)}%`}
                hint={metrics.approval_rate === null ? "No decisions yet" : undefined}
              />
              <KpiCard label="Deployed models" value={metrics.deployed_model_count} />
            </>
          )}
        </AsyncSection>
      </section>

      <section className="page-section">
        <h2>Alerts</h2>
        <AsyncSection state={alertsState} emptyMessage="No open alerts.">
          {(alerts) => (
            <ul className="alert-list">
              {alerts.map((alert) => (
                <li key={alert.id} className={`alert-list__item alert-list__item--${alert.severity}`}>
                  <strong>{alert.severity.toUpperCase()}</strong> {alert.message}
                </li>
              ))}
            </ul>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}
