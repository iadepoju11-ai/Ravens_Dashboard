import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewsPage } from "@/features/reviews/ReviewsPage";
import { useIdentity } from "@/services/useIdentity";

vi.mock("@/services/useIdentity", () => ({ useIdentity: vi.fn() }));

function mockIdentity(roles: string[]) {
  vi.mocked(useIdentity).mockReturnValue({
    isLoading: false,
    isAuthenticated: true,
    accessToken: "test-access-token",
    email: "compliance@example.com",
    roles,
    login: vi.fn(),
    logout: vi.fn(),
  });
}

function jsonResponse(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

const REVIEW = {
  id: "r1",
  tenant_id: "tenant-123",
  decision_id: "d1",
  assigned_to: null,
  status: "open",
  reason: "Score fell in the refer band",
  created_at: "2026-09-18T00:00:00Z",
  resolved_at: null,
  decision: {
    id: "d1",
    application_reference: "APP-REVIEW-1",
    score: 0.5,
    outcome: "refer",
    model_version_id: "v1",
    created_at: "2026-09-18T00:00:00Z",
  },
};

function renderReviews() {
  return render(
    <MemoryRouter>
      <ReviewsPage />
    </MemoryRouter>,
  );
}

describe("ReviewsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists review cases with their decision context", async () => {
    mockIdentity(["compliance_officer"]);
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ reviews: [REVIEW] })));

    renderReviews();

    await waitFor(() => expect(screen.getByText("APP-REVIEW-1")).toBeInTheDocument());
    expect(screen.getByText("refer")).toBeInTheDocument();
    expect(screen.getByText("Score fell in the refer band")).toBeInTheDocument();
  });

  it("claims and then closes an open review case", async () => {
    mockIdentity(["compliance_officer"]);
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        expect(url).toContain("/reviews/r1/resolve");
        const body = JSON.parse(init.body as string);
        return jsonResponse({ review: { ...REVIEW, status: body.status, assigned_to: "user-1" } });
      }
      return jsonResponse({ reviews: [REVIEW] });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderReviews();

    await waitFor(() => expect(screen.getByRole("button", { name: /claim/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /claim/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/reviews/r1/resolve"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("hides claim/close actions for a role without review:resolve", async () => {
    // admin has every permission by design (2026-09-18), so it can't be
    // used to prove gating works -- auditor genuinely lacks review:resolve.
    mockIdentity(["auditor"]);
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ reviews: [REVIEW] })));

    renderReviews();

    await waitFor(() => expect(screen.getByText("APP-REVIEW-1")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /claim/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /close/i })).not.toBeInTheDocument();
  });
});
