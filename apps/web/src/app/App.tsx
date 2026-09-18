import { AuthProvider } from "react-oidc-context";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { NotYetBuiltPage } from "@/components/NotYetBuiltPage";
import { OverviewPage } from "@/features/overview/OverviewPage";
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
              <Route path="score" element={<NotYetBuiltPage title="Score" />} />
              <Route path="decisions" element={<NotYetBuiltPage title="Decisions" />} />
              <Route path="decisions/:id" element={<NotYetBuiltPage title="Decision detail" />} />
              <Route path="models" element={<NotYetBuiltPage title="Models" />} />
              <Route path="datasets" element={<NotYetBuiltPage title="Datasets" />} />
              <Route path="fairness" element={<NotYetBuiltPage title="Fairness" />} />
              <Route path="audit" element={<NotYetBuiltPage title="Audit" />} />
              <Route path="monitoring" element={<NotYetBuiltPage title="Monitoring" />} />
              <Route path="admin" element={<NotYetBuiltPage title="Admin" />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthGate>
    </AuthProvider>
  );
}
