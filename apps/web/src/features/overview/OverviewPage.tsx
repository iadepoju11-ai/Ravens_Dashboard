import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AsyncSection } from "@/components/AsyncSection";
import {
  AuditIcon,
  DatasetsIcon,
  DecisionsIcon,
  FairnessIcon,
  ModelsIcon,
  MonitoringIcon,
  ScoreIcon,
} from "@/components/icons";
import { KpiCard } from "@/components/KpiCard";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";
import {
  fetchApiHealth,
  fetchFairnessReports,
  fetchIntegrityStatus,
  fetchMetrics,
  fetchRecentAlerts,
  fetchRecentDecisions,
} from "./api";

const QUICK_LINKS = [
  { to: "/score", label: "Score an application", description: "Submit a new credit application for scoring", icon: ScoreIcon },
  { to: "/decisions", label: "View decisions", description: "Browse and search past decisions", icon: DecisionsIcon },
  { to: "/models", label: "Model registry", description: "Manage and deploy model versions", icon: ModelsIcon },
  { to: "/fairness", label: "Fairness reports", description: "Monitor fairness metrics and alerts", icon: FairnessIcon },
  { to: "/audit", label: "Audit log", description: "View tamper-evident audit events", icon: AuditIcon },
  { to: "/datasets", label: "Datasets", description: "Register and review training datasets", icon: DatasetsIcon },
];

function firstNamePart(email: string | undefined): string {
  if (!email) return "there";
  return email.split("@")[0].split(/[._-]/)[0];
}

export function OverviewPage() {
  // App.tsx only ever renders this page once useIdentity().isAuthenticated
  // is true, so accessToken is assumed present here -- no "please log in"
  // branch needed at this level.
  const { accessToken, email } = useIdentity();

  // Metrics itself is never "empty" — decision_count really can be 0,
  // which is a fact, not a failure; approval_rate/current_model_version
  // being null (also a fact — "no data yet") is handled per-card below,
  // not by hiding the whole section.
  const metricsState = useApiResource(() => fetchMetrics(accessToken), [accessToken]);
  const decisionsState = useApiResource(() => fetchRecentDecisions(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });
  const alertsState = useApiResource(() => fetchRecentAlerts(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });
  const integrityState = useApiResource(() => fetchIntegrityStatus(accessToken), [accessToken], {
    isEmpty: (data) => data === null,
  });
  const healthState = useApiResource(() => fetchApiHealth(), []);
  const fairnessState = useApiResource(() => fetchFairnessReports(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });

  // The real moment this page's data last loaded -- not a fabricated
  // "vs last 7 days" trend, since no historical time-series endpoint
  // exists yet to back one.
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  useEffect(() => {
    if (metricsState.status === "success") setLastUpdated(new Date());
  }, [metricsState.status]);

  return (
    <div className="overview-page">
      <div className="overview-page__intro">
        <h1>Overview</h1>
        <p className="overview-page__welcome">
          Welcome back, {firstNamePart(email)}. Here's what's happening with your CreditGuard XAI platform.
        </p>
        {lastUpdated && <p className="overview-page__updated">Last updated: {lastUpdated.toLocaleString()}</p>}
      </div>

      <div className="overview-page__top-row">
        <section className="kpi-grid" aria-label="Key metrics">
          <AsyncSection state={metricsState}>
            {(metrics) => (
              <>
                <KpiCard
                  label="Total decisions"
                  value={metrics.decision_count}
                  icon={<DecisionsIcon />}
                  accent="blue"
                />
                <KpiCard
                  label="Approval rate"
                  value={metrics.approval_rate === null ? "—" : `${Math.round(metrics.approval_rate * 100)}%`}
                  hint={metrics.approval_rate === null ? "No decisions yet" : undefined}
                  icon={<ScoreIcon />}
                  accent="green"
                />
                <KpiCard
                  label="Current model version"
                  value={
                    metrics.current_model_version
                      ? `${metrics.current_model_version.model_name} v${metrics.current_model_version.version}`
                      : "—"
                  }
                  hint={metrics.current_model_version ? undefined : "No model deployed yet"}
                  icon={<ModelsIcon />}
                  accent="purple"
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
                  icon={<AuditIcon />}
                  accent="teal"
                />
              );
            }}
          </AsyncSection>

          <AsyncSection state={healthState}>
            {(health) => (
              <KpiCard
                label="API health"
                value={health.status}
                tone={health.status === "ok" ? "good" : "bad"}
                icon={<MonitoringIcon />}
                accent="teal"
              />
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
                  icon={<FairnessIcon />}
                  accent="amber"
                />
              );
            }}
          </AsyncSection>
        </section>

        <div className="hero-panel">
          <p className="hero-panel__title">Transparent AI. Fairer credit. Stronger decisions.</p>
          <p className="hero-panel__body">
            CreditGuard XAI combines machine learning, explainable AI, and governance to make credit decisions
            transparent, fair, and traceable — every score ships with the evidence behind it.
          </p>
          <Link to="/fairness">View fairness reports →</Link>
        </div>
      </div>

      <section className="overview-page__section">
        <div className="section-header">
          <h2>Recent decisions</h2>
          <Link to="/decisions">View all →</Link>
        </div>
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
        <div className="section-header">
          <h2>Recent alerts</h2>
          <Link to="/monitoring">View all →</Link>
        </div>
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
        <div className="section-header">
          <h2>Quick links</h2>
        </div>
        <ul className="quick-links">
          {QUICK_LINKS.map((link) => (
            <li key={link.to}>
              <Link to={link.to}>
                <span className="quick-link__icon">
                  <link.icon />
                </span>
                <span className="quick-link__body">
                  <span className="quick-link__title">{link.label}</span>
                  <span className="quick-link__description">{link.description}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
