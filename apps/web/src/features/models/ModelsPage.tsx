import { useState } from "react";
import { AsyncSection } from "@/components/AsyncSection";
import { useApiResource } from "@/hooks/useApiResource";
import { useMutation } from "@/hooks/useMutation";
import { hasPermission } from "@/services/permissions";
import { useIdentity } from "@/services/useIdentity";
import { approveModelVersion, deployModelVersion, fetchModels, registerModelVersion } from "./api";

function statusTone(status: string): string {
  if (status === "deployed") return "status-badge--good";
  if (status === "archived") return "status-badge--bad";
  return "status-badge";
}

export function ModelsPage() {
  const { accessToken, roles } = useIdentity();
  const canApprove = hasPermission(roles, "models:approve");
  const canDeploy = hasPermission(roles, "models:deploy");
  const canRegister = hasPermission(roles, "models:create");
  const modelsState = useApiResource(() => fetchModels(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });

  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [artifactUri, setArtifactUri] = useState("");
  const registerMutation = useMutation(registerModelVersion);
  const approveMutation = useMutation(approveModelVersion);
  const deployMutation = useMutation(deployModelVersion);

  const handleRegister = (event: React.FormEvent) => {
    event.preventDefault();
    void registerMutation
      .run(accessToken, { name, version, artifact_uri: artifactUri })
      .then((result) => {
        if (result) {
          setName("");
          setVersion("");
          setArtifactUri("");
          modelsState.reload();
        }
      });
  };

  const handleApprove = (modelVersionId: string) => {
    void approveMutation.run(accessToken, modelVersionId).then((result) => {
      if (result) modelsState.reload();
    });
  };

  const handleDeploy = (modelVersionId: string) => {
    void deployMutation.run(accessToken, modelVersionId).then((result) => {
      if (result) modelsState.reload();
    });
  };

  return (
    <div className="models-page">
      <div className="page-header">
        <h1>Models</h1>
      </div>

      <AsyncSection state={modelsState} emptyMessage="No models registered yet.">
        {(models) => (
          <table className="data-table">
            <caption className="sr-only">Registered models and versions</caption>
            <thead>
              <tr>
                <th scope="col">Model</th>
                <th scope="col">Version</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {models.flatMap((model) =>
                model.versions.map((mv) => (
                  <tr key={mv.id}>
                    <td>{model.name}</td>
                    <td>{mv.version}</td>
                    <td>
                      <span className={`status-badge ${statusTone(mv.status)}`}>{mv.status}</span>
                    </td>
                    <td>
                      {mv.status === "draft" && canApprove && (
                        <button
                          type="button"
                          className="button button--small"
                          onClick={() => handleApprove(mv.id)}
                          disabled={approveMutation.state.status === "loading"}
                        >
                          Approve
                        </button>
                      )}
                      {mv.status === "approved" && canDeploy && (
                        <button
                          type="button"
                          className="button button--small"
                          onClick={() => handleDeploy(mv.id)}
                          disabled={deployMutation.state.status === "loading"}
                        >
                          Deploy
                        </button>
                      )}
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}
      </AsyncSection>

      {(approveMutation.state.status === "error" || deployMutation.state.status === "error") && (
        <div className="async-state async-state--error" role="alert">
          {approveMutation.state.status === "error" ? approveMutation.state.error : null}
          {deployMutation.state.status === "error" ? deployMutation.state.error : null}
        </div>
      )}

      {canRegister ? (
        <section className="page-section">
          <h2>Register a model version</h2>
          <form className="form-grid" onSubmit={handleRegister}>
            <label className="field">
              Model name
              <input type="text" required value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="field">
              Version
              <input type="text" required value={version} onChange={(event) => setVersion(event.target.value)} />
            </label>
            <label className="field">
              Artifact URI
              <input
                type="text"
                required
                placeholder="file://./model_artifacts/..."
                value={artifactUri}
                onChange={(event) => setArtifactUri(event.target.value)}
              />
            </label>
            <button
              type="submit"
              className="button button--primary"
              disabled={registerMutation.state.status === "loading"}
            >
              {registerMutation.state.status === "loading" ? "Registering…" : "Register"}
            </button>
          </form>
          {registerMutation.state.status === "error" && (
            <div className="async-state async-state--error" role="alert">
              {registerMutation.state.error}
            </div>
          )}
        </section>
      ) : (
        <p className="async-state async-state--empty">
          Your role doesn't include registering model versions.
        </p>
      )}
    </div>
  );
}
