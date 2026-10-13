"use client";

import { useCallback, useEffect, useState, type DependencyList } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";

type State<T> = { data: T | null; loading: boolean; error: unknown };

/**
 * Load data for a page: `loader` is a pure async fetcher; state is only set inside promise
 * callbacks (never synchronously in the effect body), which is what React 19's rules want.
 * `reload()` re-runs the loader; the data stays on screen meanwhile.
 */
export function useLoader<T>(loader: () => Promise<T>, deps: DependencyList) {
  const [state, setState] = useState<State<T>>({ data: null, loading: true, error: null });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    loader()
      .then((data) => {
        if (alive) setState({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (!alive) return;
        setState((s) => ({ ...s, loading: false, error }));
        toast.error(errorMessage(error));
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps are the caller's, plus the reload tick
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data: state.data, loading: state.loading, error: state.error, reload };
}
