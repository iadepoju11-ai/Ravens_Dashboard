import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DatasetsPage } from "@/features/datasets/DatasetsPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token", roles: ["compliance_officer"] }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("DatasetsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("authorizes via the bearer token, now that this endpoint is OIDC-migrated", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        const headers = new Headers(init?.headers);
        expect(headers.get("Authorization")).toBe("Bearer test-access-token");
        return jsonResponse({
          datasets: [
            {
              id: "ds1",
              tenant_id: "tenant-123",
              name: "home-credit",
              created_at: "2026-09-18T00:00:00Z",
              versions: [{ id: "dv1", dataset_id: "ds1", version: "v1", uri: "s3://x", row_count: 1000, created_at: "2026-09-18T00:00:00Z" }],
            },
          ],
        });
      }),
    );

    render(<DatasetsPage />);

    await waitFor(() => expect(screen.getByText("home-credit")).toBeInTheDocument());
    expect(screen.getByText("1000")).toBeInTheDocument();
  });
});
