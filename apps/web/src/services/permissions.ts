// Mirrors app/security/permissions.py's ROLE_PERMISSIONS -- a UI-only
// hint for which actions to *show*, kept in sync by hand. The backend is
// the only real enforcement point (every route calls require_permission()
// itself, independent of anything the client claims); if this drifts out
// of sync, the worst case is a button that's shown but 403s on click, or
// one that's hidden but would have worked -- never a security gap, since
// nothing here bypasses the backend check.
const CREDIT_ANALYST_PERMISSIONS = ["decisions:create", "decisions:read", "tenant:read"];

const COMPLIANCE_OFFICER_PERMISSIONS = [
  "decisions:read",
  "models:read",
  "models:create",
  "models:approve",
  "models:deploy",
  "datasets:read",
  "datasets:create",
  "monitoring:read",
  "fairness:read",
  "fairness:review",
  "review:read",
  "review:resolve",
  "tenant:read",
];

const AUDITOR_PERMISSIONS = ["audit:read", "audit:export", "audit:verify", "tenant:read"];

const DATA_PROTECTION_OFFICER_PERMISSIONS = ["datasets:read", "audit:read", "tenant:read"];

// Full access to every page and feature, by explicit request (2026-09-18)
// -- a union of every other role's permissions plus the two admin-only
// ones, same approach as the backend, so a permission added to any other
// role here is automatically visible to admin too.
const ADMIN_PERMISSIONS = [
  "users:manage",
  "tenant:manage",
  ...new Set([
    ...CREDIT_ANALYST_PERMISSIONS,
    ...COMPLIANCE_OFFICER_PERMISSIONS,
    ...AUDITOR_PERMISSIONS,
    ...DATA_PROTECTION_OFFICER_PERMISSIONS,
  ]),
];

const ROLE_PERMISSIONS: Record<string, readonly string[]> = {
  admin: ADMIN_PERMISSIONS,
  credit_analyst: CREDIT_ANALYST_PERMISSIONS,
  compliance_officer: COMPLIANCE_OFFICER_PERMISSIONS,
  auditor: AUDITOR_PERMISSIONS,
  data_protection_officer: DATA_PROTECTION_OFFICER_PERMISSIONS,
};

export function hasPermission(roles: readonly string[], permission: string): boolean {
  return roles.some((role) => ROLE_PERMISSIONS[role]?.includes(permission));
}
