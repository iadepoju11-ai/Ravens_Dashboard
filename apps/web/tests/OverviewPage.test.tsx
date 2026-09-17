import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { TenantProvider } from "@/services/tenantContext";

const TENANT_STORAGE_KEY = "creditguard.devTenantId";

function renderOverview() {
  return render(
    <MemoryRouter>
      <TenantProvider>
        <OverviewPage />
      </TenantProvider>
    </MemoryRouter>,
  );
}

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const EMPTY_METRICS = {
  decision_count: 0,
  approved_count: 0,
  approval_rate: null,
  deployed_model_count: 0,
  current_model_version: null,
};

function stubFetch(overrides: Record<string, unknown> = {}) {
  const responses: Record<string, unknown> = {
    "/monitoring/metrics": { metrics: EMPTY_METRICS },
    "/decisions": { decisions: [] },
    "/monitoring/alerts": { alerts: [] },
    "/audit/integrity-status": { latest_check: null },
    "/health": { status: "ok" },
    "/fairness/reports": { reports: [] },
    ...overrides,
  };

  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const match = Object.keys(responses).find((path) => url.includes(path));
      if (match) return jsonResponse(responses[match]);
      return Promise.reject(new Error(`unexpected fetch: ${url}`));
    }),
  );
}

describe("OverviewPage", () => {
  beforeEach(() => {
    window.localStorage.setItem(TENANT_STORAGE_KEY, "tenant-123");
  });

  afterEach(() => {
    window.localStorage.removeItem(TENANT_STORAGE_KEY);
    vi.unstubAllGlobals();
  });

  it("prompts for a tenant id when none is set, instead of guessing one", () => {
    window.localStorage.removeItem(TENANT_STORAGE_KEY);

    renderOverview();

    expect(screen.getByText(/enter a tenant id/i)).toBeInTheDocument();
  });

  it("renders real KPI data once every request resolves", async () => {
    stubFetch({
      "/monitoring/metrics": {
        metrics: {
          decision_count: 10,
          approved_count: 6,
          approval_rate: 0.6,
          deployed_model_count: 1,
          current_model_version: {
            model_id: "m1",
            model_name: "credit-risk",
            model_version_id: "v1",
            version: "1.0.0",
          },
        },
      },
    });

    renderOverview();

    await waitFor(() => expect(screen.getByText("10")).toBeInTheDocument());
    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.getByText(/credit-risk v1\.0\.0/)).toBeInTheDocument();
  });

  it("shows an explicit unavailable state, never a fake 0, when a backend call fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network down"))));

    renderOverview();

    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0));
    expect(screen.queryByText("10")).not.toBeInTheDocument();
  });

  it("shows null approval_rate as an explicit unknown, not 0%", async () => {
    stubFetch();

    renderOverview();

    await waitFor(() => expect(screen.getByText("No decisions yet")).toBeInTheDocument());
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("shows an explicit 'no evaluation yet' state for fairness, not a fake pass", async () => {
    stubFetch();

    renderOverview();

    await waitFor(() =>
      expect(screen.getByText(/no fairness evaluation has run/i)).toBeInTheDocument(),
    );
  });

  it("shows the latest fairness result with context, never as a bare verdict", async () => {
    stubFetch({
      "/fairness/reports": {
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
            created_at: "2026-09-17T00:00:00Z",
          },
        ],
      },
    });

    renderOverview();

    await waitFor(() => expect(screen.getByText("Outside threshold")).toBeInTheDocument());
    expect(screen.getByText(/not a legal verdict/i)).toBeInTheDocument();
  });
});
