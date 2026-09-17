import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/services/apiClient";

// A shared shape for loading/error/empty/success so every page renders
// these four states the same way (CHECKLIST.md Phase 6) instead of each
// component inventing its own ad hoc spinner/error text.
export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "empty" }
  | { status: "success"; data: T };

interface Options<T> {
  // Lets a page decide what "no data" means for its own resource (e.g.
  // an empty array vs. a metrics object with a null field) rather than
  // this hook guessing.
  isEmpty?: (data: T) => boolean;
}

export function useApiResource<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  options: Options<T> = {},
): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });

    fetcher()
      .then((data) => {
        if (cancelled) return;
        setState(options.isEmpty?.(data) ? { status: "empty" } : { status: "success", data });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message = error instanceof ApiError ? error.message : "Unable to reach the API";
        setState({ status: "error", error: message });
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadToken]);

  return { ...state, reload };
}
