import type { ReactNode } from "react";
import type { AsyncState } from "@/hooks/useApiResource";

interface Props<T> {
  state: AsyncState<T>;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
}

// The one place loading/error/empty states are rendered, so every KPI
// and table on the page looks the same instead of each one inventing its
// own spinner/error text (CHECKLIST.md Phase 6: "consistent loading /
// error / empty / insufficient-data states").
export function AsyncSection<T>({ state, emptyMessage = "No data yet.", children }: Props<T>) {
  if (state.status === "loading") {
    return (
      <div className="async-state async-state--loading" role="status">
        Loading…
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="async-state async-state--error" role="alert">
        Unavailable — {state.error}
      </div>
    );
  }

  if (state.status === "empty") {
    return <div className="async-state async-state--empty">{emptyMessage}</div>;
  }

  return <>{children(state.data)}</>;
}
