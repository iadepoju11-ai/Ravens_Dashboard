import { NavLink, Outlet } from "react-router-dom";
import { useTenant } from "@/services/useTenant";

const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true },
  { to: "/score", label: "Score" },
  { to: "/decisions", label: "Decisions" },
  { to: "/models", label: "Models" },
  { to: "/datasets", label: "Datasets" },
  { to: "/fairness", label: "Fairness" },
  { to: "/audit", label: "Audit" },
  { to: "/monitoring", label: "Monitoring" },
  { to: "/admin", label: "Admin" },
];

export function AppShell() {
  const { tenantId, setTenantId } = useTenant();

  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <div className="app-shell__brand">CreditGuard XAI</div>
        <nav className="app-shell__nav" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? "app-shell__nav-link is-active" : "app-shell__nav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="app-shell__tenant">
          <label htmlFor="dev-tenant-id">Tenant ID (dev only, no auth yet)</label>
          <input
            id="dev-tenant-id"
            type="text"
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
            placeholder="paste a tenant id"
          />
        </div>
      </header>
      <main className="app-shell__content">
        <Outlet />
      </main>
    </div>
  );
}
