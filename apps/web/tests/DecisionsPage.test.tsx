import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DecisionsPage } from "@/features/decisions/DecisionsPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token" }),
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

        if (url.includes("/models")) {
          return jsonResponse({ models: [] });
        }

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

  it("filters by model version, refetching decisions with the selected id", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/models")) {
        return jsonResponse({
          models: [
            {
              id: "m1",
              tenant_id: "tenant-123",
              name: "credit-risk",
              created_at: "2026-09-18T00:00:00Z",
              versions: [
                {
                  id: "v1",
                  model_id: "m1",
                  version: "1.0.0",
                  status: "deployed",
                  artifact_uri: "file://x",
                  metrics: null,
                  created_at: "2026-09-18T00:00:00Z",
                },
              ],
            },
          ],
        });
      }
      return jsonResponse({ decisions: [] });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <DecisionsPage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/no decisions match/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/model version/i), { target: { value: "v1" } });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("model_version_id=v1"), expect.anything()),
    );
    expect(screen.getByRole("button", { name: /clear filters/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /clear filters/i }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /clear filters/i })).not.toBeInTheDocument(),
    );
  });
});
