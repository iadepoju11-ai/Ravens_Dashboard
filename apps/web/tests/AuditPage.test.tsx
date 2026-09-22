import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuditPage } from "@/features/audit/AuditPage";
import { useIdentity } from "@/services/useIdentity";

vi.mock("@/services/useIdentity", () => ({ useIdentity: vi.fn() }));

function mockIdentity(roles: string[]) {
  vi.mocked(useIdentity).mockReturnValue({
    isLoading: false,
    isAuthenticated: true,
    accessToken: "test-access-token",
    email: "auditor@example.com",
    roles,
    login: vi.fn(),
    logout: vi.fn(),
  });
}

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("AuditPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists events and runs a real chain verification on demand", async () => {
    mockIdentity(["auditor"]);
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/audit/verify-chain")) {
        return jsonResponse({
          valid: true,
          events_checked: 2,
          first_event_id: "e1",
          last_event_id: "e2",
          failures: [],
          integrity_check_id: "c1",
        });
      }
      if (url.includes("/audit/integrity-status")) {
        return jsonResponse({ latest_check: null });
      }
      return jsonResponse({
        events: [
          {
            id: "e1",
            tenant_id: "tenant-123",
            event_type: "decision.created",
            entity_type: "decision",
            entity_id: "d1",
            hash: "abcdef1234567890",
            prev_hash: null,
            created_at: "2026-09-18T00:00:00Z",
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AuditPage />);

    await waitFor(() => expect(screen.getByText("decision.created")).toBeInTheDocument());
    expect(screen.getByText(/no audit check has run yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /verify chain/i }));

    await waitFor(() => expect(screen.getByText(/verified 2 event/i)).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/audit/verify-chain"), expect.anything());
  });

  it("exports the audit log as a downloaded JSON file", async () => {
    mockIdentity(["auditor"]);
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/audit/export")) {
        expect(url).toContain("date_from=2026-01-01");
        return jsonResponse({
          events: [
            {
              id: "e1",
              tenant_id: "tenant-123",
              event_type: "decision.created",
              entity_type: "decision",
              entity_id: "d1",
              hash: "abcdef1234567890",
              prev_hash: null,
              created_at: "2026-09-18T00:00:00Z",
              payload: { score: 0.5 },
            },
          ],
          meta: {
            exported_by: "user-1",
            exported_at: "2026-09-18T01:00:00Z",
            scope: { date_from: "2026-01-01", date_to: null },
            event_count: 1,
            export_event_id: "e2",
          },
        });
      }
      if (url.includes("/audit/integrity-status")) {
        return jsonResponse({ latest_check: null });
      }
      return jsonResponse({ events: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn(() => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<AuditPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /^export$/i })).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/^from$/i), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: /^export$/i }));

    await waitFor(() => expect(screen.getByText(/exported 1 event/i)).toBeInTheDocument());
    expect(createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();

    clickSpy.mockRestore();
  });

  it("hides verify and export actions for a role without audit:verify/audit:export", async () => {
    mockIdentity(["credit_analyst"]);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/audit/integrity-status")) return jsonResponse({ latest_check: null });
        return jsonResponse({ events: [] });
      }),
    );

    render(<AuditPage />);

    await waitFor(() => expect(screen.getByText(/no audit events recorded yet/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /verify chain/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /export audit log/i })).not.toBeInTheDocument();
  });
});
