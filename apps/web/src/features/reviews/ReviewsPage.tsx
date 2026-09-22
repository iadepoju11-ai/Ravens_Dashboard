import { useState } from "react";
import { Link } from "react-router-dom";
import { AsyncSection } from "@/components/AsyncSection";
import { useApiResource } from "@/hooks/useApiResource";
import { useMutation } from "@/hooks/useMutation";
import { hasPermission } from "@/services/permissions";
import { useIdentity } from "@/services/useIdentity";
import type { ReviewCaseStatus } from "@/types/api";
import { fetchReviews, resolveReview } from "./api";

const STATUSES: ReviewCaseStatus[] = ["open", "in_review", "closed"];

function statusTone(status: ReviewCaseStatus): string {
  if (status === "closed") return "status-badge--good";
  if (status === "open") return "status-badge--bad";
  return "status-badge";
}

export function ReviewsPage() {
  const { accessToken, roles } = useIdentity();
  const canResolve = hasPermission(roles, "review:resolve");
  const [status, setStatus] = useState<ReviewCaseStatus | "">("");

  const reviewsState = useApiResource(() => fetchReviews(accessToken, status || undefined), [accessToken, status], {
    isEmpty: (data) => data.length === 0,
  });
  const resolveMutation = useMutation(resolveReview);

  const handleResolve = (reviewId: string, nextStatus: "in_review" | "closed") => {
    void resolveMutation.run(accessToken, reviewId, nextStatus).then((result) => {
      if (result) reviewsState.reload();
    });
  };

  return (
    <div className="reviews-page">
      <div className="page-header">
        <h1>Reviews</h1>
      </div>
      <p>
        Opened automatically when a decision's score falls in the refer band, or when the deciding model version
        has a failing fairness evaluation on record — see the model card / fairness reports for what "failing"
        means for a given model version.
      </p>

      <div className="filters-bar">
        <label className="field">
          Status
          <select value={status} onChange={(event) => setStatus(event.target.value as ReviewCaseStatus | "")}>
            <option value="">All</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>
      </div>

      {resolveMutation.state.status === "error" && (
        <div className="async-state async-state--error" role="alert">
          {resolveMutation.state.error}
        </div>
      )}

      <AsyncSection state={reviewsState} emptyMessage="No review cases match these filters.">
        {(reviews) => (
          <table className="data-table">
            <caption className="sr-only">Review cases</caption>
            <thead>
              <tr>
                <th scope="col">Application</th>
                <th scope="col">Outcome</th>
                <th scope="col">Score</th>
                <th scope="col">Reason</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {reviews.map((review) => (
                <tr key={review.id}>
                  <td>
                    {review.decision ? (
                      <Link to={`/decisions/${review.decision.id}`}>{review.decision.application_reference}</Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {review.decision ? (
                      <span className={`outcome-badge outcome-badge--${review.decision.outcome}`}>
                        {review.decision.outcome}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{review.decision ? review.decision.score.toFixed(3) : "—"}</td>
                  <td>{review.reason}</td>
                  <td>
                    <span className={`status-badge ${statusTone(review.status)}`}>
                      {review.status.replace("_", " ")}
                    </span>
                  </td>
                  <td>
                    {canResolve && review.status === "open" && (
                      <>
                        <button
                          type="button"
                          className="button button--small"
                          onClick={() => handleResolve(review.id, "in_review")}
                          disabled={resolveMutation.state.status === "loading"}
                        >
                          Claim
                        </button>{" "}
                        <button
                          type="button"
                          className="button button--small"
                          onClick={() => handleResolve(review.id, "closed")}
                          disabled={resolveMutation.state.status === "loading"}
                        >
                          Close
                        </button>
                      </>
                    )}
                    {canResolve && review.status === "in_review" && (
                      <button
                        type="button"
                        className="button button--small"
                        onClick={() => handleResolve(review.id, "closed")}
                        disabled={resolveMutation.state.status === "loading"}
                      >
                        Close
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </AsyncSection>
    </div>
  );
}
