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
  login: () => void;
  logout: () => void;
}

export function useIdentity(): Identity {
  const auth = useAuth();

  return {
    isLoading: auth.isLoading,
    isAuthenticated: auth.isAuthenticated,
    accessToken: auth.user?.access_token,
    email: auth.user?.profile.email,
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
