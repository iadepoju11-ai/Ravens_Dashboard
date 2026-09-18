import { useState } from "react";
import { AsyncSection } from "@/components/AsyncSection";
import { useApiResource } from "@/hooks/useApiResource";
import { useMutation } from "@/hooks/useMutation";
import { useIdentity } from "@/services/useIdentity";
import { fetchDatasets, registerDataset } from "./api";

export function DatasetsPage() {
  const { accessToken } = useIdentity();
  const datasetsState = useApiResource(() => fetchDatasets(accessToken), [accessToken], {
    isEmpty: (data) => data.length === 0,
  });

  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [uri, setUri] = useState("");
  const registerMutation = useMutation(registerDataset);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    void registerMutation.run(accessToken, { name, version, uri }).then((result) => {
      if (result) {
        setName("");
        setVersion("");
        setUri("");
        datasetsState.reload();
      }
    });
  };

  return (
    <div className="datasets-page">
      <div className="page-header">
        <h1>Datasets</h1>
      </div>

      <AsyncSection state={datasetsState} emptyMessage="No datasets registered yet.">
        {(datasets) => (
          <table className="data-table">
            <caption className="sr-only">Registered datasets and versions</caption>
            <thead>
              <tr>
                <th scope="col">Dataset</th>
                <th scope="col">Version</th>
                <th scope="col">Rows</th>
                <th scope="col">URI</th>
              </tr>
            </thead>
            <tbody>
              {datasets.flatMap((dataset) =>
                dataset.versions.map((dv) => (
                  <tr key={dv.id}>
                    <td>{dataset.name}</td>
                    <td>{dv.version}</td>
                    <td>{dv.row_count ?? "—"}</td>
                    <td>{dv.uri}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}
      </AsyncSection>

      <section className="page-section">
        <h2>Register a dataset version</h2>
        <form className="form-grid" onSubmit={handleSubmit}>
          <label className="field">
            Dataset name
            <input type="text" required value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="field">
            Version
            <input type="text" required value={version} onChange={(event) => setVersion(event.target.value)} />
          </label>
          <label className="field">
            URI
            <input type="text" required value={uri} onChange={(event) => setUri(event.target.value)} />
          </label>
          <button type="submit" className="button button--primary" disabled={registerMutation.state.status === "loading"}>
            {registerMutation.state.status === "loading" ? "Registering…" : "Register"}
          </button>
        </form>
        {registerMutation.state.status === "error" && (
          <div className="async-state async-state--error" role="alert">
            {registerMutation.state.error}
          </div>
        )}
      </section>
    </div>
  );
}
