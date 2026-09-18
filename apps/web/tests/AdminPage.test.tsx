import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminPage } from "@/features/admin/AdminPage";

vi.mock("@/services/useIdentity", () => ({
  useIdentity: () => ({ accessToken: "test-access-token", email: "admin@example.com" }),
}));

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

describe("AdminPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the caller's own tenant, since no admin CRUD endpoint exists yet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        jsonResponse({ tenants: [{ id: "tenant-123", name: "Demo Bank", slug: "demo-bank", is_active: true, created_at: "2026-09-18T00:00:00Z" }] }),
      ),
    );

    render(<AdminPage />);

    await waitFor(() => expect(screen.getByText("Demo Bank")).toBeInTheDocument());
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("admin@example.com")).toBeInTheDocument();
  });
});
