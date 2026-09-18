import type { AuthProviderProps } from "react-oidc-context";

// Authorization Code + PKCE against the `creditguard-web` client (public,
// no client secret -- see infra/keycloak/creditguard-realm.json). Keycloak
// locally, swappable for an enterprise IdP later: nothing outside this
// file needs to change, since the rest of the app only ever reads
// identity through useIdentity() (see useIdentity.ts), never react-oidc-
// context directly.
//
// authority must be the *host-side* Keycloak address -- a browser can
// never reach the `keycloak` Docker service name, and Keycloak is pinned
// (KC_HOSTNAME, docker-compose.yml) to present this same address as
// every token's issuer regardless of who's asking, so the API validates
// against the identical string. See docs/architecture/oidc-rbac.md.
export const oidcConfig: AuthProviderProps = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY ?? "http://localhost:8081/realms/creditguard",
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID ?? "creditguard-web",
  redirect_uri: import.meta.env.VITE_OIDC_REDIRECT_URI ?? "http://localhost:5173/",
  scope: "openid profile email",
  // Strips the ?code=...&state=... query string Keycloak appends after
  // the redirect back, so a page refresh doesn't try to replay a
  // one-time authorization code.
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};
