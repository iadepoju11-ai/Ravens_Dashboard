import type { ReactNode } from "react";
import { useAuth } from "react-oidc-context";

// Gates the whole app behind a real login, rather than each page having
// its own "please sign in" branch — CHECKLIST.md Phase 6's replacement
// for the dev-only manually-entered tenant ID. Every page below this
// (OverviewPage, etc.) can assume useIdentity().isAuthenticated is true.
export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth();

  if (auth.isLoading) {
    return (
      <div className="auth-gate">
        <p>Signing you in…</p>
      </div>
    );
  }

  if (auth.error) {
    return (
      <div className="auth-gate" role="alert">
        <p>Sign-in failed: {auth.error.message}</p>
        <button type="button" onClick={() => void auth.signinRedirect()}>
          Try again
        </button>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <div className="auth-gate">
        <h1>CreditGuard XAI</h1>
        <p>Sign in to continue.</p>
        <button type="button" onClick={() => void auth.signinRedirect()}>
          Sign in
        </button>
      </div>
    );
  }

  return <>{children}</>;
}
