import { useCallback, useState } from "react";
import { ApiError } from "@/services/apiClient";

// Companion to useApiResource for POST-ish actions (score, register,
// approve, deploy, verify): the same loading/error shape, but triggered
// explicitly by the caller instead of running on mount.
export type MutationState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "success"; data: T };

export function useMutation<Args extends unknown[], T>(action: (...args: Args) => Promise<T>) {
  const [state, setState] = useState<MutationState<T>>({ status: "idle" });

  const run = useCallback(
    async (...args: Args) => {
      setState({ status: "loading" });
      try {
        const data = await action(...args);
        setState({ status: "success", data });
        return data;
      } catch (error) {
        const message = error instanceof ApiError ? error.message : "Unable to reach the API";
        setState({ status: "error", error: message });
        return undefined;
      }
    },
    // action is expected to be stable enough per call site (a closure
    // built fresh each render is fine -- react's exhaustive-deps would
    // just cause an extra re-memoization, not a bug); intentionally not
    // listed to keep call sites from needing useCallback everywhere.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const reset = useCallback(() => setState({ status: "idle" }), []);

  return { state, run, reset };
}
