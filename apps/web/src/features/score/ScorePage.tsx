import { useState } from "react";
import { useMutation } from "@/hooks/useMutation";
import { useIdentity } from "@/services/useIdentity";
import { scoreApplication } from "./api";

interface FeatureRow {
  name: string;
  value: string;
}

// Numeric-looking input is sent as a number (most model features are
// numeric), everything else as a string -- the backend's own validation
// (ScoringService._validate_features) is the real authority on what's
// acceptable; this is just a reasonable default, not a schema.
function coerceFeatureValue(value: string): number | string {
  if (value.trim() !== "" && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  return value;
}

export function ScorePage() {
  const { accessToken } = useIdentity();
  const [applicationReference, setApplicationReference] = useState("");
  const [rows, setRows] = useState<FeatureRow[]>([{ name: "", value: "" }]);
  const { state, run, reset } = useMutation(scoreApplication);

  const updateRow = (index: number, field: keyof FeatureRow, value: string) => {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  };

  const addRow = () => setRows((current) => [...current, { name: "", value: "" }]);
  const removeRow = (index: number) => setRows((current) => current.filter((_, i) => i !== index));

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const features = Object.fromEntries(
      rows.filter((row) => row.name.trim() !== "").map((row) => [row.name, coerceFeatureValue(row.value)]),
    );
    void run(accessToken, { application_reference: applicationReference, features });
  };

  return (
    <div className="score-page">
      <div className="page-header">
        <h1>Score an application</h1>
      </div>

      <form className="form-grid" onSubmit={handleSubmit}>
        <label className="field">
          Application reference
          <input
            type="text"
            required
            value={applicationReference}
            onChange={(event) => setApplicationReference(event.target.value)}
          />
        </label>

        <fieldset>
          <legend>Features</legend>
          {rows.map((row, index) => (
            <div className="feature-row" key={index}>
              <input
                type="text"
                placeholder="feature name"
                aria-label="Feature name"
                value={row.name}
                onChange={(event) => updateRow(index, "name", event.target.value)}
              />
              <input
                type="text"
                placeholder="value"
                aria-label="Feature value"
                value={row.value}
                onChange={(event) => updateRow(index, "value", event.target.value)}
              />
              <button
                type="button"
                className="button button--small"
                onClick={() => removeRow(index)}
                disabled={rows.length === 1}
              >
                Remove
              </button>
            </div>
          ))}
          <button type="button" className="button button--small" onClick={addRow}>
            Add feature
          </button>
        </fieldset>

        <button type="submit" className="button button--primary" disabled={state.status === "loading"}>
          {state.status === "loading" ? "Scoring…" : "Score application"}
        </button>
      </form>

      {state.status === "error" && (
        <div className="async-state async-state--error" role="alert">
          {state.error}
        </div>
      )}

      {state.status === "success" && (
        <section className="page-section">
          <div className="page-header">
            <h2>Result</h2>
            <button type="button" className="button button--small" onClick={reset}>
              Score another
            </button>
          </div>
          <dl className="detail-grid">
            <div>
              <dt>Outcome</dt>
              <dd>
                <span className={`outcome-badge outcome-badge--${state.data.decision.outcome}`}>
                  {state.data.decision.outcome}
                </span>
              </dd>
            </div>
            <div>
              <dt>Score</dt>
              <dd>{state.data.decision.score.toFixed(3)}</dd>
            </div>
            <div>
              <dt>Decision ID</dt>
              <dd>{state.data.decision.id}</dd>
            </div>
          </dl>
          {state.data.explanation && (
            <>
              <h3>Top reasons</h3>
              <ol className="reason-code-list">
                {state.data.explanation.reason_codes.map((reason) => (
                  <li key={reason.feature} className={`reason-code-list__item reason-code-list__item--${reason.direction}`}>
                    <span className="reason-code-list__label">{reason.label}</span>
                    <span className="reason-code-list__direction">
                      {reason.direction === "increased_risk" ? "increased risk" : "decreased risk"}
                    </span>
                    <span className="reason-code-list__contribution">{reason.contribution.toFixed(4)}</span>
                  </li>
                ))}
              </ol>

              <h3>All feature attributions ({state.data.explanation.method})</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Feature</th>
                    <th scope="col">Attribution</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(state.data.explanation.feature_attributions).map(([feature, value]) => (
                    <tr key={feature}>
                      <td>{feature}</td>
                      <td>{value.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}
    </div>
  );
}
