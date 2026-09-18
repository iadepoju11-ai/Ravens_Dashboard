import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionsPage } from "@/features/decisions/DecisionsPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token", tenantId: "tenant-123" }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("DecisionsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders real decisions with a bearer token, not the X-Tenant-Id header", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const headers = new Headers(init?.headers);
        expect(headers.get("Authorization")).toBe("Bearer test-access-token");
        expect(url).toContain("/decisions?");
        return jsonResponse({
          decisions: [
            {
              id: "d1",
              tenant_id: "tenant-123",
              model_version_id: "v1",
              application_reference: "APP-1",
              request_id: "r1",
              score: 0.9,
              outcome: "decline",
              created_at: "2026-09-18T00:00:00Z",
            },
          ],
        });
      }),
    );

    render(
      <MemoryRouter>
        <DecisionsPage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText("APP-1")).toBeInTheDocument());
    expect(screen.getByRole("cell", { name: "decline" })).toBeInTheDocument();
  });
});
