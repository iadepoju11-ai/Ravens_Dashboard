import { useState } from "react";
import { Link } from "react-router-dom";
import { AsyncSection } from "@/components/AsyncSection";
import { fetchModels } from "@/features/models/api";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";
import type { DecisionOutcome } from "@/types/api";
import { fetchDecisions } from "./api";

const OUTCOMES: DecisionOutcome[] = ["approve", "refer", "decline"];

export function DecisionsPage() {
  const { accessToken } = useIdentity();
  const [outcome, setOutcome] = useState<DecisionOutcome | "">("");
  const [modelVersionId, setModelVersionId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // Options for the model-version filter -- a separate, independent fetch
  // from the decisions list itself, so a slow/failed models call never
  // blocks the decisions table from loading.
  const modelsState = useApiResource(() => fetchModels(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });

  const decisionsState = useApiResource(
    () =>
      fetchDecisions(accessToken, {
        outcome: outcome || undefined,
        modelVersionId: modelVersionId || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      }),
    [accessToken, outcome, modelVersionId, dateFrom, dateTo],
    { isEmpty: (data) => data.length === 0 },
  );

  const hasActiveFilters = outcome !== "" || modelVersionId !== "" || dateFrom !== "" || dateTo !== "";
  const clearFilters = () => {
    setOutcome("");
    setModelVersionId("");
    setDateFrom("");
    setDateTo("");
  };

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

        <label className="field">
          Model version
          <select value={modelVersionId} onChange={(event) => setModelVersionId(event.target.value)}>
            <option value="">All</option>
            {modelsState.status === "success" &&
              modelsState.data.flatMap((model) =>
                model.versions.map((version) => (
                  <option key={version.id} value={version.id}>
                    {model.name} v{version.version}
                  </option>
                )),
              )}
          </select>
        </label>

        <label className="field">
          From
          <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </label>

        <label className="field">
          To
          <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </label>

        {hasActiveFilters && (
          <button type="button" className="button button--small" onClick={clearFilters}>
            Clear filters
          </button>
        )}
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
