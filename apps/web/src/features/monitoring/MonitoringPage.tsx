import { AsyncSection } from "@/components/AsyncSection";
import { KpiCard } from "@/components/KpiCard";
import { fetchMetrics, fetchRecentAlerts } from "@/features/overview/api";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";

// Not yet migrated to OIDC auth (see docs/architecture/oidc-rbac.md) --
// reuses the Overview page's fetchers, which already send both
// accessToken and tenantId; this endpoint only honours tenantId today.
export function MonitoringPage() {
  const { accessToken, tenantId } = useIdentity();
  const auth = { accessToken, tenantId };

  const metricsState = useApiResource(() => fetchMetrics(auth), [accessToken, tenantId]);
  const alertsState = useApiResource(() => fetchRecentAlerts(auth), [accessToken, tenantId], {
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
