import { AsyncSection } from "@/components/AsyncSection";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";
import { fetchFairnessReports } from "./api";

export function FairnessPage() {
  const { accessToken } = useIdentity();
  const state = useApiResource(() => fetchFairnessReports(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });

  return (
    <div className="fairness-page">
      <div className="page-header">
        <h1>Fairness</h1>
      </div>
      <p>
        A statistical check against one configured metric and threshold — not a legal or ethical verdict. See
        CLAUDE.md: fairness monitoring, legal compliance, and policy review are different things.
      </p>

      <AsyncSection
        state={state}
        emptyMessage="No fairness evaluation has run for this tenant yet — this is not the same as 'fair', it means no monitoring has happened."
      >
        {(reports) => (
          <table className="data-table">
            <caption className="sr-only">Fairness evaluations</caption>
            <thead>
              <tr>
                <th scope="col">Model version</th>
                <th scope="col">Protected attribute</th>
                <th scope="col">Metric</th>
                <th scope="col">Value</th>
                <th scope="col">Threshold</th>
                <th scope="col">Result</th>
                <th scope="col">Evaluated</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.id}>
                  <td>{report.model_version_id}</td>
                  <td>{report.protected_attribute}</td>
                  <td>{report.metric_name}</td>
                  <td>{report.metric_value.toFixed(4)}</td>
                  <td>{report.threshold}</td>
                  <td>
                    <span className={`status-badge ${report.passed ? "status-badge--good" : "status-badge--bad"}`}>
                      {report.passed ? "Within threshold" : "Outside threshold"}
                    </span>
                  </td>
                  <td>{new Date(report.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </AsyncSection>
    </div>
  );
}
