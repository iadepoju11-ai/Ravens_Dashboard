import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModelsPage } from "@/features/models/ModelsPage";
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

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

const MODELS_RESPONSE = {
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
          status: "draft",
          artifact_uri: "file://x.pkl",
          metrics: null,
          created_at: "2026-09-18T00:00:00Z",
        },
      ],
    },
  ],
};

describe("ModelsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists model versions and approves a draft one", async () => {
    mockIdentity(["compliance_officer"]);
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        expect(url).toContain("/models/v1/approve");
        return jsonResponse({ model_version: { ...MODELS_RESPONSE.models[0].versions[0], status: "approved" } });
      }
      return jsonResponse(MODELS_RESPONSE);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ModelsPage />);

    await waitFor(() => expect(screen.getByText("credit-risk")).toBeInTheDocument());
    expect(screen.getByText("draft")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/models/v1/approve"), expect.anything()),
    );
  });

  it("shows a clear message when registering fails", async () => {
    mockIdentity(["compliance_officer"]);
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        if (init?.method === "POST") return jsonResponse({ error: "name, version, and artifact_uri are required" }, 400);
        return jsonResponse({ models: [] });
      }),
    );

    render(<ModelsPage />);

    await waitFor(() => expect(screen.getByText(/no models registered/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/model name/i), { target: { value: "credit-risk" } });
    fireEvent.change(screen.getByLabelText(/^version$/i), { target: { value: "1.0.0" } });
    fireEvent.change(screen.getByLabelText(/artifact uri/i), { target: { value: "file://x.pkl" } });
    fireEvent.click(screen.getByRole("button", { name: /^register$/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/required/i));
  });

  it("hides the approve action and the register form for a role without models:approve/models:create", async () => {
    mockIdentity(["credit_analyst"]);
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse(MODELS_RESPONSE)));

    render(<ModelsPage />);

    await waitFor(() => expect(screen.getByText("credit-risk")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^register$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/doesn't include registering model versions/i)).toBeInTheDocument();
  });
});
