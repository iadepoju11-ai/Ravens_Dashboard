import { useContext } from "react";
import { TenantContext, type TenantContextValue } from "./tenantContext";

export function useTenant(): TenantContextValue {
  const context = useContext(TenantContext);
  if (!context) {
    throw new Error("useTenant must be used within a TenantProvider");
  }
  return context;
}
