import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MonitoringPage } from "@/features/monitoring/MonitoringPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token", tenantId: "tenant-123" }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("MonitoringPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders metrics and open alerts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/monitoring/metrics")) {
          return jsonResponse({
            metrics: {
              decision_count: 5,
              approved_count: 2,
              approval_rate: 0.4,
              deployed_model_count: 1,
              current_model_version: null,
            },
          });
        }
        return jsonResponse({
          alerts: [
            { id: "a1", tenant_id: "tenant-123", alert_type: "x", severity: "high", message: "Something failed", status: "open", created_at: "2026-09-18T00:00:00Z", resolved_at: null },
          ],
        });
      }),
    );

    render(<MonitoringPage />);

    await waitFor(() => expect(screen.getByText("5")).toBeInTheDocument());
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("Something failed")).toBeInTheDocument();
  });
});
