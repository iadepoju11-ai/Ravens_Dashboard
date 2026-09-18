import type { KeyboardEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { FloatingBackdrop } from "@/components/FloatingBackdrop";
import {
  AdminIcon,
  AuditIcon,
  BellIcon,
  DatasetsIcon,
  DecisionsIcon,
  FairnessIcon,
  HomeIcon,
  ModelsIcon,
  MonitoringIcon,
  ScoreIcon,
  SearchIcon,
  ShieldIcon,
} from "@/components/icons";
import { apiFetch } from "@/services/apiClient";
import { useIdentity } from "@/services/useIdentity";
import type { MonitoringAlert } from "@/types/api";

const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true, icon: HomeIcon },
  { to: "/score", label: "Score", icon: ScoreIcon },
  { to: "/decisions", label: "Decisions", icon: DecisionsIcon },
  { to: "/models", label: "Models", icon: ModelsIcon },
  { to: "/datasets", label: "Datasets", icon: DatasetsIcon },
  { to: "/fairness", label: "Fairness", icon: FairnessIcon },
  { to: "/audit", label: "Audit", icon: AuditIcon },
  { to: "/monitoring", label: "Monitoring", icon: MonitoringIcon },
  { to: "/admin", label: "Admin", icon: AdminIcon },
];

function initialsFor(email: string | undefined): string {
  if (!email) return "?";
  const name = email.split("@")[0];
  const parts = name.split(/[._-]/).filter(Boolean);
  const chars = parts.length >= 2 ? [parts[0][0], parts[1][0]] : [name.slice(0, 2)];
  return chars.join("").toUpperCase().slice(0, 2);
}

// A real jump-to-page search over the app's own 9 routes -- not a
// pretend full-text search over decisions/models/datasets, since no
// backend endpoint for that exists. Filtering the known nav labels is
// honest about what it actually does.
function PageSearch() {
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const matches =
    query.trim() === ""
      ? []
      : NAV_ITEMS.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase()));

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function go(to: string) {
    navigate(to);
    setQuery("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (matches.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((current) => (current + 1) % matches.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((current) => (current - 1 + matches.length) % matches.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(matches[highlighted]?.to ?? matches[0].to);
    } else if (event.key === "Escape") {
      setQuery("");
    }
  }

  return (
    <div className="topbar__search" ref={containerRef}>
      <SearchIcon />
      <input
        type="search"
        placeholder="Jump to a page…"
        aria-label="Search pages"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setHighlighted(0);
        }}
        onKeyDown={handleKeyDown}
      />
      {query.trim() === "" && <span className="topbar__search-hint">⌘K</span>}
      {matches.length > 0 && (
        <ul className="topbar__search-results">
          {matches.map((item, index) => (
            <li key={item.to}>
              <a
                href={item.to}
                className={index === highlighted ? "is-highlighted" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  go(item.to);
                }}
              >
                {item.label}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function IdentityMenu() {
  const { email, logout } = useIdentity();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="topbar__identity" ref={containerRef}>
      <button
        type="button"
        className="topbar__identity-trigger"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="true"
        aria-expanded={open}
      >
        <span className="topbar__avatar">{initialsFor(email)}</span>
        <span className="topbar__identity-label">
          <span className="topbar__identity-email">{email ?? "Signed in"}</span>
        </span>
      </button>
      {open && (
        <div className="topbar__identity-menu" role="menu">
          <button type="button" onClick={logout} role="menuitem">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function NotificationBell() {
  const { accessToken } = useIdentity();
  const [openAlertCount, setOpenAlertCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<{ alerts: MonitoringAlert[] }>("/monitoring/alerts", { accessToken })
      .then((response) => {
        if (!cancelled) setOpenAlertCount(response.alerts.filter((a) => a.status === "open").length);
      })
      .catch(() => {
        // A failed background alert-count fetch shouldn't break the
        // whole shell -- the Monitoring page itself surfaces the real
        // error state if this keeps failing.
        if (!cancelled) setOpenAlertCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  return (
    <NavLink to="/monitoring" className="topbar__icon-button" aria-label="Open alerts">
      <BellIcon />
      {openAlertCount !== null && openAlertCount > 0 && (
        <span className="topbar__badge">{openAlertCount > 9 ? "9+" : openAlertCount}</span>
      )}
    </NavLink>
  );
}

export function AppShell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <ShieldIcon width={22} height={22} />
          <span>
            CreditGuard <span className="sidebar__brand-accent">XAI</span>
          </span>
        </div>
        <nav className="sidebar__nav" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? "sidebar__nav-link is-active" : "sidebar__nav-link")}
            >
              <item.icon />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer">
          <span className="sidebar__status-dot" />
          System healthy
        </div>
      </aside>

      <div className="app-shell__main">
        <header className="topbar">
          <PageSearch />
          <div className="topbar__actions">
            <NotificationBell />
            <IdentityMenu />
          </div>
        </header>
        <main className="app-shell__content">
          <FloatingBackdrop variant="ambient" />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
