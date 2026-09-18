import { useAuth } from "react-oidc-context";

// The one place the rest of the app reads "who is logged in" -- nothing
// outside this file (and authConfig.ts) knows react-oidc-context exists,
// same reasoning as the backend's app/security/identity.py: swapping the
// OIDC library or provider later is a change here, not a grep across
// every page for useAuth().
//
// tenantId comes from the token's tenant_id claim (see
// infra/keycloak/creditguard-realm.json's protocol mapper) -- it is
// informational for the frontend only. The backend never trusts it from
// here; every migrated endpoint (see docs/architecture/oidc-rbac.md)
// derives tenant identity itself from the verified access token, not
// from anything this hook exposes. It's only read by this app to still
// populate the X-Tenant-Id header the handful of not-yet-migrated
// endpoints (monitoring, datasets) require.
export interface Identity {
  isLoading: boolean;
  isAuthenticated: boolean;
  accessToken: string | undefined;
  tenantId: string | undefined;
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
    tenantId: typeof auth.user?.profile.tenant_id === "string" ? auth.user.profile.tenant_id : undefined,
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
