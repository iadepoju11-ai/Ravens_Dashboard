import { useState } from "react";
import { Link } from "react-router-dom";
import { AsyncSection } from "@/components/AsyncSection";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";
import type { DecisionOutcome } from "@/types/api";
import { fetchDecisions } from "./api";

const OUTCOMES: DecisionOutcome[] = ["approve", "refer", "decline"];

export function DecisionsPage() {
  const { accessToken } = useIdentity();
  const [outcome, setOutcome] = useState<DecisionOutcome | "">("");

  const decisionsState = useApiResource(
    () => fetchDecisions(accessToken, { outcome: outcome || undefined }),
    [accessToken, outcome],
    { isEmpty: (data) => data.length === 0 },
  );

  return (
    <div className="decisions-page">
      <div className="page-header">
        <h1>Decisions</h1>
      </div>

      <div className="filters-bar">
        <label className="field">
          Outcome
          <select value={outcome} onChange={(event) => setOutcome(event.target.value as DecisionOutcome | "")}>
            <option value="">All</option>
            {OUTCOMES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      </div>

      <AsyncSection state={decisionsState} emptyMessage="No decisions match these filters.">
        {(decisions) => (
          <table className="data-table">
            <caption className="sr-only">Decisions</caption>
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
                  <td>
                    <Link to={`/decisions/${decision.id}`}>{decision.application_reference}</Link>
                  </td>
                  <td>
                    <span className={`outcome-badge outcome-badge--${decision.outcome}`}>{decision.outcome}</span>
                  </td>
                  <td>{decision.score.toFixed(3)}</td>
                  <td>{new Date(decision.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </AsyncSection>
    </div>
  );
}
