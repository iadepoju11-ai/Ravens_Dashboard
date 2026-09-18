import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuditPage } from "@/features/audit/AuditPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token", tenantId: "tenant-123" }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("AuditPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists events and runs a real chain verification on demand", async () => {
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
});
