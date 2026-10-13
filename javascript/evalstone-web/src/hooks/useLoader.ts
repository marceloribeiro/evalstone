"use client";

import { useCallback, useEffect, useState, type DependencyList } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";

type State<T> = { key: string; data: T | null; error: unknown };

/**
 * Load data for a page: `loader` is a pure async fetcher; state is only set inside promise
 * callbacks (never synchronously in the effect body), which is what React 19's rules want.
 * `loading` is derived: true whenever the data on hand belongs to other deps (or an older
 * `reload()` tick) than the current ones — so a deps change shows as loading while the previous
 * data stays available for a stale-while-loading render. `deps` must be JSON-serialisable
 * (ids, strings, numbers, booleans).
 */
export function useLoader<T>(loader: () => Promise<T>, deps: DependencyList) {
  const [tick, setTick] = useState(0);
  const key = JSON.stringify([...deps, tick]);
  const [state, setState] = useState<State<T>>({ key: "", data: null, error: null });

  useEffect(() => {
    let alive = true;
    loader()
      .then((data) => {
        if (alive) setState({ key, data, error: null });
      })
      .catch((error) => {
        if (!alive) return;
        setState((s) => ({ key, data: s.data, error }));
        toast.error(errorMessage(error));
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` encodes the caller's deps and the reload tick
  }, [key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const loading = state.key !== key;
  return { data: state.data, loading, error: loading ? null : state.error, reload };
}
