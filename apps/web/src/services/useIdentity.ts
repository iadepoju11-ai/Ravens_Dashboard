import { useAuth } from "react-oidc-context";

// The one place the rest of the app reads "who is logged in" -- nothing
// outside this file (and authConfig.ts) knows react-oidc-context exists,
// same reasoning as the backend's app/security/identity.py: swapping the
// OIDC library or provider later is a change here, not a grep across
// every page for useAuth().
//
// No tenantId here: every endpoint is OIDC-migrated (see
// docs/architecture/oidc-rbac.md), so tenant identity is always derived
// server-side from the verified access token. The token does carry a
// tenant_id claim (infra/keycloak/creditguard-realm.json's protocol
// mapper), but nothing in this app needs to read it client-side --
// add it back here if a page ever needs to display it.
export interface Identity {
  isLoading: boolean;
  isAuthenticated: boolean;
  accessToken: string | undefined;
  email: string | undefined;
  // Decoded client-side from the access token's own payload, without
  // verifying its signature -- fine for a UI hint (which buttons to show),
  // never a security boundary. The backend independently verifies the
  // token and re-derives permissions itself (app/security/permissions.py)
  // on every request regardless of what the UI decided to render.
  roles: readonly string[];
  login: () => void;
  logout: () => void;
}

function decodeRolesFromAccessToken(accessToken: string | undefined): readonly string[] {
  const payloadSegment = accessToken?.split(".")[1];
  if (!payloadSegment) return [];

  try {
    const base64 = payloadSegment.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const claims = JSON.parse(atob(padded)) as { realm_access?: { roles?: string[] } };
    return claims.realm_access?.roles ?? [];
  } catch {
    // A malformed/unexpected token shape degrades to "no roles" (every
    // gated action stays hidden) rather than throwing and breaking the
    // whole page -- the backend's own 403 is still the real guard.
    return [];
  }
}

export function useIdentity(): Identity {
  const auth = useAuth();

  return {
    isLoading: auth.isLoading,
    isAuthenticated: auth.isAuthenticated,
    accessToken: auth.user?.access_token,
    email: auth.user?.profile.email,
    roles: decodeRolesFromAccessToken(auth.user?.access_token),
    login: () => {
      void auth.signinRedirect();
    },
    logout: () => {
      // A local sign-out (clears this app's session) rather than a full
      // OIDC RP-initiated logout (which needs post_logout_redirect_uri
      // registered on the Keycloak client) -- good enough for local dev,
      // revisit if a real single-logout requirement shows up.
      void auth.removeUser();
    },
  };
}
