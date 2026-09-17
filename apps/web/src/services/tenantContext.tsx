import { createContext, useState, type ReactNode } from "react";

// Dev-only stand-in for real tenant identity. There is no authentication
// yet (ERD Phase 6) — the backend takes tenant identity from an
// X-Tenant-Id header with no verification behind it, so this is exactly
// as trustworthy as that header is today. Replace with a value derived
// from an authenticated session once real auth exists; nothing else in
// this app should need to change when that happens, since everything
// reads the tenant id from this context (via useTenant, in its own file
// so Fast Refresh can still treat this file as component-only).
const STORAGE_KEY = "creditguard.devTenantId";

export interface TenantContextValue {
  tenantId: string;
  setTenantId: (id: string) => void;
}

// Small context+provider pair by design; splitting the context object
// into its own file too only helps Fast Refresh granularity, not
// correctness.
// eslint-disable-next-line react-refresh/only-export-components
export const TenantContext = createContext<TenantContextValue | undefined>(undefined);

function readStoredTenantId(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function TenantProvider({ children }: { children: ReactNode }) {
  const [tenantId, setTenantIdState] = useState<string>(readStoredTenantId);

  const setTenantId = (id: string) => {
    setTenantIdState(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // A private window or blocked storage just means the choice won't
      // persist across reloads — not a functional failure.
    }
  };

  return <TenantContext.Provider value={{ tenantId, setTenantId }}>{children}</TenantContext.Provider>;
}
