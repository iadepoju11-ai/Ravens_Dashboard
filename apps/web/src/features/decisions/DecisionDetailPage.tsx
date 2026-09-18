import { useParams } from "react-router-dom";
import { AsyncSection } from "@/components/AsyncSection";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";
import { fetchDecision } from "./api";

export function DecisionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { accessToken } = useIdentity();

  const state = useApiResource(() => fetchDecision(accessToken, id ?? ""), [accessToken, id]);

  return (
    <div className="decision-detail-page">
      <div className="page-header">
        <h1>Decision detail</h1>
      </div>

      <AsyncSection state={state}>
        {({ decision, explanation }) => (
          <>
            <dl className="detail-grid">
              <div>
                <dt>Application</dt>
                <dd>{decision.application_reference}</dd>
              </div>
              <div>
                <dt>Outcome</dt>
                <dd>
                  <span className={`outcome-badge outcome-badge--${decision.outcome}`}>{decision.outcome}</span>
                </dd>
              </div>
              <div>
                <dt>Score</dt>
                <dd>{decision.score.toFixed(3)}</dd>
              </div>
              <div>
                <dt>Model version</dt>
                <dd>{decision.model_version_id}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{new Date(decision.created_at).toLocaleString()}</dd>
              </div>
            </dl>

            {explanation ? (
              <>
                <h2>Feature attributions ({explanation.method})</h2>
                <p>Base value: {explanation.base_value.toFixed(3)}</p>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Feature</th>
                      <th scope="col">Attribution</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(explanation.feature_attributions).map(([feature, value]) => (
                      <tr key={feature}>
                        <td>{feature}</td>
                        <td>{value.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <p>No explanation recorded for this decision.</p>
            )}
          </>
        )}
      </AsyncSection>
    </div>
  );
}
