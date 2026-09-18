import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FairnessPage } from "@/features/fairness/FairnessPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token", tenantId: "tenant-123" }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("FairnessPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the fairness result with context, never as a bare verdict", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({
          reports: [
            {
              id: "f1",
              tenant_id: "tenant-123",
              model_version_id: "v1",
              protected_attribute: "sex",
              metric_name: "demographic_parity_difference",
              metric_value: 0.12,
              threshold: 0.1,
              passed: false,
              created_at: "2026-09-18T00:00:00Z",
            },
          ],
        }),
      ),
    );

    render(<FairnessPage />);

    await waitFor(() => expect(screen.getByText("Outside threshold")).toBeInTheDocument());
    expect(screen.getByText("sex")).toBeInTheDocument();
    expect(screen.getByText(/not a legal.*verdict/i)).toBeInTheDocument();
  });
});
