import { Link } from "react-router-dom";
import { AsyncSection } from "@/components/AsyncSection";
import { KpiCard } from "@/components/KpiCard";
import { useApiResource } from "@/hooks/useApiResource";
import { useTenant } from "@/services/useTenant";
import {
  fetchApiHealth,
  fetchFairnessReports,
  fetchIntegrityStatus,
  fetchMetrics,
  fetchRecentAlerts,
  fetchRecentDecisions,
} from "./api";

export function OverviewPage() {
  const { tenantId } = useTenant();

  // Metrics itself is never "empty" — decision_count really can be 0,
  // which is a fact, not a failure; approval_rate/current_model_version
  // being null (also a fact — "no data yet") is handled per-card below,
  // not by hiding the whole section.
  const metricsState = useApiResource(() => fetchMetrics(tenantId), [tenantId]);
  const decisionsState = useApiResource(() => fetchRecentDecisions(tenantId), [tenantId], {
    isEmpty: (data) => data.length === 0,
  });
  const alertsState = useApiResource(() => fetchRecentAlerts(tenantId), [tenantId], {
    isEmpty: (data) => data.length === 0,
  });
  const integrityState = useApiResource(() => fetchIntegrityStatus(tenantId), [tenantId], {
    isEmpty: (data) => data === null,
  });
  const healthState = useApiResource(() => fetchApiHealth(), []);
  const fairnessState = useApiResource(() => fetchFairnessReports(tenantId), [tenantId], {
    isEmpty: (data) => data.length === 0,
  });

  if (!tenantId) {
    return (
      <p className="overview-page__prompt">
        Enter a tenant ID above to load the overview — there is no authentication yet, so tenant
        identity has to be set manually for now.
      </p>
    );
  }

  return (
    <div className="overview-page">
      <h1>Overview</h1>

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
              <KpiCard
                label="Current model version"
                value={
                  metrics.current_model_version
                    ? `${metrics.current_model_version.model_name} v${metrics.current_model_version.version}`
                    : "—"
                }
                hint={metrics.current_model_version ? undefined : "No model deployed yet"}
              />
            </>
          )}
        </AsyncSection>

        <AsyncSection state={integrityState} emptyMessage="No audit check has run yet.">
          {(check) => {
            // isEmpty already routes a null check to the "empty" branch
            // above — this narrows the type for TypeScript, it can't
            // actually be null here.
            if (!check) return null;
            return (
              <KpiCard
                label="Audit integrity"
                value={check.valid ? "Valid" : "FAILED"}
                tone={check.valid ? "good" : "bad"}
                hint={`as of last check, ${new Date(check.created_at).toLocaleString()}`}
              />
            );
          }}
        </AsyncSection>

        <AsyncSection state={healthState}>
          {(health) => (
            <KpiCard label="API health" value={health.status} tone={health.status === "ok" ? "good" : "bad"} />
          )}
        </AsyncSection>

        <AsyncSection
          state={fairnessState}
          emptyMessage="No fairness evaluation has run for this tenant yet — this is not the same as 'fair', it means no monitoring has happened."
        >
          {(reports) => {
            const latest = reports[0];
            // A statistical pass/fail on one metric, not a legal or
            // ethical verdict — see CLAUDE.md: fairness monitoring, legal
            // compliance, and policy review are different things.
            return (
              <KpiCard
                label="Fairness (latest check)"
                value={latest.passed ? "Within threshold" : "Outside threshold"}
                tone={latest.passed ? "good" : "warning"}
                hint={`${latest.metric_name} on ${latest.protected_attribute}, threshold ${latest.threshold} — not a legal verdict`}
              />
            );
          }}
        </AsyncSection>
      </section>

      <section className="overview-page__section">
        <h2>Recent decisions</h2>
        <AsyncSection state={decisionsState} emptyMessage="No decisions recorded yet for this tenant.">
          {(decisions) => (
            <table className="data-table">
              <caption className="sr-only">Recent decisions</caption>
              <thead>
                <tr>
                  <th scope="col">Application</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Score</th>
                  <th scope="col">Created</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((decision) => (
                  <tr key={decision.id}>
                    <td>{decision.application_reference}</td>
                    <td>
                      <span className={`outcome-badge outcome-badge--${decision.outcome}`}>
                        {decision.outcome}
                      </span>
                    </td>
                    <td>{decision.score.toFixed(3)}</td>
                    <td>{new Date(decision.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </AsyncSection>
      </section>

      <section className="overview-page__section">
        <h2>Recent alerts</h2>
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

      <section className="overview-page__section">
        <h2>Quick links</h2>
        <ul className="quick-links">
          <li>
            <Link to="/score">Score an application</Link>
          </li>
          <li>
            <Link to="/decisions">All decisions</Link>
          </li>
          <li>
            <Link to="/models">Model registry</Link>
          </li>
          <li>
            <Link to="/audit">Audit log</Link>
          </li>
        </ul>
      </section>
    </div>
  );
}
