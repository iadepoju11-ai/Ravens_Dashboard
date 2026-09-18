import { AsyncSection } from "@/components/AsyncSection";
import { useApiResource } from "@/hooks/useApiResource";
import { useMutation } from "@/hooks/useMutation";
import { useIdentity } from "@/services/useIdentity";
import { fetchAuditEvents, fetchIntegrityStatus, verifyChain, verifyEvent } from "./api";

export function AuditPage() {
  const { accessToken } = useIdentity();
  const eventsState = useApiResource(() => fetchAuditEvents(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });
  const integrityState = useApiResource(() => fetchIntegrityStatus(accessToken), [accessToken], {
    isEmpty: (data) => data === null,
  });
  const verifyChainMutation = useMutation(verifyChain);
  const verifyEventMutation = useMutation(verifyEvent);

  const handleVerifyChain = () => {
    void verifyChainMutation.run(accessToken).then(() => integrityState.reload());
  };

  return (
    <div className="audit-page">
      <div className="page-header">
        <h1>Audit</h1>
        <button
          type="button"
          className="button button--primary"
          onClick={handleVerifyChain}
          disabled={verifyChainMutation.state.status === "loading"}
        >
          {verifyChainMutation.state.status === "loading" ? "Verifying…" : "Verify chain"}
        </button>
      </div>

      <section className="page-section">
        <h2>Integrity status</h2>
        <AsyncSection state={integrityState} emptyMessage="No audit check has run yet.">
          {(check) =>
            check && (
              <p>
                <span className={`status-badge ${check.valid ? "status-badge--good" : "status-badge--bad"}`}>
                  {check.valid ? "Valid" : "FAILED"}
                </span>{" "}
                as of {new Date(check.created_at).toLocaleString()}
              </p>
            )
          }
        </AsyncSection>
        {verifyChainMutation.state.status === "success" && (
          <p>
            Verified {verifyChainMutation.state.data.events_checked} event(s) —{" "}
            {verifyChainMutation.state.data.valid ? "chain intact" : `${verifyChainMutation.state.data.failures.length} failure(s) found`}
            .
          </p>
        )}
        {verifyChainMutation.state.status === "error" && (
          <div className="async-state async-state--error" role="alert">
            {verifyChainMutation.state.error}
          </div>
        )}
      </section>

      <section className="page-section">
        <h2>Events</h2>
        <AsyncSection state={eventsState} emptyMessage="No audit events recorded yet.">
          {(events) => (
            <table className="data-table">
              <caption className="sr-only">Audit events</caption>
              <thead>
                <tr>
                  <th scope="col">Event type</th>
                  <th scope="col">Entity</th>
                  <th scope="col">Hash</th>
                  <th scope="col">Created</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id}>
                    <td>{event.event_type}</td>
                    <td>
                      {event.entity_type} {event.entity_id}
                    </td>
                    <td title={event.hash}>{event.hash.slice(0, 12)}…</td>
                    <td>{new Date(event.created_at).toLocaleString()}</td>
                    <td>
                      <button
                        type="button"
                        className="button button--small"
                        onClick={() => void verifyEventMutation.run(accessToken, event.id)}
                        disabled={verifyEventMutation.state.status === "loading"}
                      >
                        Verify
                      </button>
                      {verifyEventMutation.state.status === "success" &&
                        verifyEventMutation.state.data.event_id === event.id && (
                          <span
                            className={`status-badge ${
                              verifyEventMutation.state.data.valid ? "status-badge--good" : "status-badge--bad"
                            }`}
                          >
                            {verifyEventMutation.state.data.valid ? "valid" : "hash mismatch"}
                          </span>
                        )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}
