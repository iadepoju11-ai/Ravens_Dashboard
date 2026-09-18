import { NavLink, Outlet } from "react-router-dom";
import { useIdentity } from "@/services/useIdentity";

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
  const { email, logout } = useIdentity();

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
        <div className="app-shell__identity">
          <span>{email ?? "Signed in"}</span>
          <button type="button" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="app-shell__content">
        <Outlet />
      </main>
    </div>
  );
}
