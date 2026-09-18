import { AuthProvider } from "react-oidc-context";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AdminPage } from "@/features/admin/AdminPage";
import { AuditPage } from "@/features/audit/AuditPage";
import { DatasetsPage } from "@/features/datasets/DatasetsPage";
import { DecisionDetailPage } from "@/features/decisions/DecisionDetailPage";
import { DecisionsPage } from "@/features/decisions/DecisionsPage";
import { FairnessPage } from "@/features/fairness/FairnessPage";
import { ModelsPage } from "@/features/models/ModelsPage";
import { MonitoringPage } from "@/features/monitoring/MonitoringPage";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { ScorePage } from "@/features/score/ScorePage";
import { oidcConfig } from "@/services/authConfig";
import { AppShell } from "./AppShell";
import { AuthGate } from "./AuthGate";

export function App() {
  return (
    <AuthProvider {...oidcConfig}>
      <AuthGate>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<OverviewPage />} />
              <Route path="score" element={<ScorePage />} />
              <Route path="decisions" element={<DecisionsPage />} />
              <Route path="decisions/:id" element={<DecisionDetailPage />} />
              <Route path="models" element={<ModelsPage />} />
              <Route path="datasets" element={<DatasetsPage />} />
              <Route path="fairness" element={<FairnessPage />} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="monitoring" element={<MonitoringPage />} />
              <Route path="admin" element={<AdminPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthGate>
    </AuthProvider>
  );
}
