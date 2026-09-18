import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionDetailPage } from "@/features/decisions/DecisionDetailPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token" }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("DecisionDetailPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the decision and its feature attributions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        expect(url).toContain("/decisions/d1");
        return jsonResponse({
          decision: {
            id: "d1",
            tenant_id: "tenant-123",
            model_version_id: "v1",
            application_reference: "APP-42",
            request_id: "r1",
            score: 0.31,
            outcome: "approve",
            created_at: "2026-09-18T00:00:00Z",
          },
          explanation: {
            id: "e1",
            decision_id: "d1",
            method: "shap-tree",
            base_value: 0.5,
            feature_attributions: { income: 0.12 },
            created_at: "2026-09-18T00:00:00Z",
          },
        });
      }),
    );

    render(
      <MemoryRouter initialEntries={["/decisions/d1"]}>
        <Routes>
          <Route path="/decisions/:id" element={<DecisionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("APP-42")).toBeInTheDocument());
    expect(screen.getByText("approve")).toBeInTheDocument();
    expect(screen.getByText("income")).toBeInTheDocument();
  });
});
