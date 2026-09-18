import { AsyncSection } from "@/components/AsyncSection";
import { useApiResource } from "@/hooks/useApiResource";
import { useIdentity } from "@/services/useIdentity";
import { fetchOwnTenant } from "./api";

// Honestly minimal: no user/role/tenant-management endpoints exist yet
// (app/api/v1/tenants.py only ever returns the caller's own tenant, on
// purpose -- see its docstring). This shows that one real thing rather
// than a fake CRUD UI with nothing behind it.
export function AdminPage() {
  const { tenantId, email } = useIdentity();
  const tenantState = useApiResource(() => fetchOwnTenant(tenantId), [tenantId]);

  return (
    <div className="admin-page">
      <div className="page-header">
        <h1>Admin</h1>
      </div>

      <AsyncSection state={tenantState}>
        {(tenant) => (
          <dl className="detail-grid">
            <div>
              <dt>Tenant</dt>
              <dd>{tenant.name}</dd>
            </div>
            <div>
              <dt>Slug</dt>
              <dd>{tenant.slug}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <span className={`status-badge ${tenant.is_active ? "status-badge--good" : "status-badge--bad"}`}>
                  {tenant.is_active ? "Active" : "Inactive"}
                </span>
              </dd>
            </div>
            <div>
              <dt>Signed in as</dt>
              <dd>{email}</dd>
            </div>
          </dl>
        )}
      </AsyncSection>

      <p>
        User and role management aren't built yet — there's no backend endpoint for either. This page will grow
        into that once one exists, rather than showing controls with nothing behind them.
      </p>
    </div>
  );
}
