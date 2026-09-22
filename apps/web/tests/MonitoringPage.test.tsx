import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MonitoringPage } from "@/features/monitoring/MonitoringPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token" }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const EMPTY_HISTOGRAM = { count: 0, sum_seconds: 0, avg_ms: null, p50_ms: null, p95_ms: null };

const OBSERVABILITY_RESPONSE = {
  observability: {
    http: {
      total_requests: 120,
      requests_by_status: { "200": 118, "500": 2 },
      error_rate: 0.0167,
      unhandled_exceptions: 1,
      latency: { count: 119, sum_seconds: 6.0, avg_ms: 50, p50_ms: 40, p95_ms: 95 },
    },
    scoring: {
      requests_by_outcome: { approve: 10, refer: 3, decline: 2 },
      runtime_errors: 0,
      duration: { count: 15, sum_seconds: 1.5, avg_ms: 100, p50_ms: 90, p95_ms: 150 },
    },
    model_inference: { duration: EMPTY_HISTOGRAM },
    explanation: { duration: EMPTY_HISTOGRAM },
    database: { errors: 0, query_duration: EMPTY_HISTOGRAM },
    outbox: { events_by_status: {} },
    governance: { results_by_outcome: { true: 14, false: 1 } },
    review_cases: { opened_by_reason: { refer_outcome: 3 } },
  },
};

function stubFetch(overrides: Record<string, unknown> = {}) {
  const responses: Record<string, unknown> = {
    "/monitoring/metrics": {
      metrics: {
        decision_count: 5,
        approved_count: 2,
        approval_rate: 0.4,
        deployed_model_count: 1,
        current_model_version: null,
      },
    },
    "/monitoring/observability": OBSERVABILITY_RESPONSE,
    "/monitoring/alerts": {
      alerts: [
        {
          id: "a1",
          tenant_id: "tenant-123",
          alert_type: "x",
          severity: "high",
          message: "Something failed",
          status: "open",
          created_at: "2026-09-18T00:00:00Z",
          resolved_at: null,
        },
      ],
    },
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

describe("MonitoringPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders metrics and open alerts", async () => {
    stubFetch();

    render(<MonitoringPage />);

    await waitFor(() => expect(screen.getByText("5")).toBeInTheDocument());
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText("Something failed")).toBeInTheDocument();
  });

  it("renders real system-health observability data, not placeholders", async () => {
    stubFetch();

    render(<MonitoringPage />);

    await waitFor(() => expect(screen.getByText("120")).toBeInTheDocument());
    expect(screen.getByText("2%")).toBeInTheDocument(); // error_rate rounded
    expect(screen.getByText("approve: 10, refer: 3, decline: 2")).toBeInTheDocument();
    expect(screen.getByText("90.0 ms")).toBeInTheDocument(); // scoring p50
  });

  it("shows an explicit empty state for a histogram with no observations yet", async () => {
    stubFetch();

    render(<MonitoringPage />);

    await waitFor(() => expect(screen.getByText("Model inference")).toBeInTheDocument());
    // model_inference/explanation/database all use EMPTY_HISTOGRAM above --
    // average/p50/p95 must render as an explicit "no data" dash, never a
    // fabricated 0ms.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
