import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScorePage } from "@/features/score/ScorePage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token", roles: ["credit_analyst"] }),
}));

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

describe("ScorePage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("submits the form and renders the returned decision and explanation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        expect(url).toContain("/score");
        const body = JSON.parse(init?.body as string);
        expect(body.application_reference).toBe("APP-1");
        expect(body.features).toEqual({ income: 0.5 });
        return jsonResponse({
          decision: {
            id: "d1",
            tenant_id: "tenant-123",
            model_version_id: "v1",
            application_reference: "APP-1",
            request_id: "r1",
            score: 0.42,
            outcome: "refer",
            created_at: "2026-09-18T00:00:00Z",
          },
          explanation: {
            id: "e1",
            decision_id: "d1",
            method: "shap-tree",
            base_value: 0.5,
            feature_attributions: { income: -0.08 },
            reason_codes: [
              { rank: 1, feature: "income", label: "income", contribution: -0.08, direction: "decreased_risk" },
            ],
            created_at: "2026-09-18T00:00:00Z",
          },
        });
      }),
    );

    render(<ScorePage />);

    fireEvent.change(screen.getByLabelText(/application reference/i), { target: { value: "APP-1" } });
    fireEvent.change(screen.getByLabelText(/feature name/i), { target: { value: "income" } });
    fireEvent.change(screen.getByLabelText(/feature value/i), { target: { value: "0.5" } });
    fireEvent.click(screen.getByRole("button", { name: /score application/i }));

    await waitFor(() => expect(screen.getByText("refer")).toBeInTheDocument());
    expect(screen.getByText("0.420")).toBeInTheDocument();
    expect(screen.getByText("decreased risk")).toBeInTheDocument();
    expect(screen.getAllByText("income").length).toBeGreaterThan(0);
  });

  it("shows a clear message, not a crash, when the caller lacks permission", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ error: "You do not have permission to perform this action" }, 403)));

    render(<ScorePage />);

    fireEvent.change(screen.getByLabelText(/application reference/i), { target: { value: "APP-1" } });
    fireEvent.click(screen.getByRole("button", { name: /score application/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/permission/i));
  });
});
