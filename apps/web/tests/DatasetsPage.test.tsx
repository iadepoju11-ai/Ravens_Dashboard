import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DatasetsPage } from "@/features/datasets/DatasetsPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token", tenantId: "tenant-123" }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("DatasetsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the X-Tenant-Id header, since this endpoint isn't OIDC-migrated yet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        const headers = new Headers(init?.headers);
        expect(headers.get("X-Tenant-Id")).toBe("tenant-123");
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
