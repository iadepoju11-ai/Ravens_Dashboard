import { AsyncSection } from "@/components/AsyncSection";
import { DecisionsIcon, ModelsIcon, ScoreIcon } from "@/components/icons";
import { KpiCard } from "@/components/KpiCard";
import { fetchMetrics, fetchObservability, fetchRecentAlerts } from "@/features/overview/api";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";
import type { HistogramSummary } from "@/types/api";

function formatMs(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} ms`;
}

function formatCount(record: Record<string, number>): string {
  const entries = Object.entries(record);
  if (entries.length === 0) return "No data yet";
  return entries.map(([key, count]) => `${key}: ${count}`).join(", ");
}

// One small stat block (a heading + a detail-grid of key/value pairs) --
// reused for every category below instead of hand-writing the same
// dl/dt/dd structure six times.
function StatBlock({
  title,
  stats,
}: {
  title: string;
  stats: { label: string; value: string }[];
}) {
  return (
    <div>
      <h3>{title}</h3>
      <dl className="detail-grid">
        {stats.map((stat) => (
          <div key={stat.label}>
            <dt>{stat.label}</dt>
            <dd>{stat.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function durationStats(label: string, duration: HistogramSummary): { label: string; value: string }[] {
  return [
    { label: `${label} — observations`, value: String(duration.count) },
    { label: `${label} — average`, value: formatMs(duration.avg_ms) },
    { label: `${label} — p50`, value: formatMs(duration.p50_ms) },
    { label: `${label} — p95`, value: formatMs(duration.p95_ms) },
  ];
}

// Migrated to OIDC auth (monitoring:read -- see docs/architecture/oidc-rbac.md).
// Reuses the Overview page's fetchers.
export function MonitoringPage() {
  const { accessToken } = useIdentity();

  const metricsState = useApiResource(() => fetchMetrics(accessToken), [accessToken]);
  const alertsState = useApiResource(() => fetchRecentAlerts(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });
  const observabilityState = useApiResource(() => fetchObservability(accessToken), [accessToken]);

  return (
    <div className="monitoring-page">
      <div className="page-header">
        <h1>Monitoring</h1>
      </div>

      <section className="kpi-grid" aria-label="Key metrics">
        <AsyncSection state={metricsState}>
          {(metrics) => (
            <>
              <KpiCard label="Total decisions" value={metrics.decision_count} icon={<DecisionsIcon />} accent="blue" />
              <KpiCard
                label="Approval rate"
                value={metrics.approval_rate === null ? "—" : `${Math.round(metrics.approval_rate * 100)}%`}
                hint={metrics.approval_rate === null ? "No decisions yet" : undefined}
                icon={<ScoreIcon />}
                accent="green"
              />
              <KpiCard
                label="Deployed models"
                value={metrics.deployed_model_count}
                icon={<ModelsIcon />}
                accent="purple"
              />
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

      <section className="page-section">
        <h2>System health</h2>
        <p>
          Process-level metrics for this API instance since it last started — request throughput/latency,
          scoring/model/explanation duration, database query stats, outbox publish outcomes, and governance/review
          activity. The same underlying data is available in Prometheus format at <code>/metrics</code> for a real
          Prometheus/Grafana (or compatible) scrape; this view is a readable summary of it, not a separate source
          of truth.
        </p>
        <AsyncSection state={observabilityState}>
          {(observability) => (
            <div className="observability-grid">
              <StatBlock
                title="HTTP"
                stats={[
                  { label: "Total requests", value: String(observability.http.total_requests) },
                  {
                    label: "Error rate",
                    value:
                      observability.http.error_rate === null
                        ? "No requests yet"
                        : `${Math.round(observability.http.error_rate * 100)}%`,
                  },
                  { label: "Unhandled exceptions", value: String(observability.http.unhandled_exceptions) },
                  { label: "Requests by status", value: formatCount(observability.http.requests_by_status) },
                  ...durationStats("Latency", observability.http.latency),
                ]}
              />
              <StatBlock
                title="Scoring"
                stats={[
                  { label: "Requests by outcome", value: formatCount(observability.scoring.requests_by_outcome) },
                  { label: "Runtime errors", value: String(observability.scoring.runtime_errors) },
                  ...durationStats("Duration", observability.scoring.duration),
                ]}
              />
              <StatBlock
                title="Model inference"
                stats={durationStats("Duration", observability.model_inference.duration)}
              />
              <StatBlock title="Explanation" stats={durationStats("Duration", observability.explanation.duration)} />
              <StatBlock
                title="Database"
                stats={[
                  { label: "Errors", value: String(observability.database.errors) },
                  ...durationStats("Query duration", observability.database.query_duration),
                ]}
              />
              <StatBlock
                title="Outbox"
                stats={[{ label: "Events by status", value: formatCount(observability.outbox.events_by_status) }]}
              />
              <StatBlock
                title="Governance"
                stats={[
                  { label: "Results by outcome", value: formatCount(observability.governance.results_by_outcome) },
                ]}
              />
              <StatBlock
                title="Review cases"
                stats={[
                  { label: "Opened by reason", value: formatCount(observability.review_cases.opened_by_reason) },
                ]}
              />
            </div>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}
