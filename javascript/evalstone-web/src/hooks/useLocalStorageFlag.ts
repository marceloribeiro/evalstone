"use client";

import { useCallback, useSyncExternalStore } from "react";

const EVENT = "evalstone:localstorage";

function read(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

/**
 * A boolean persisted in localStorage, read via useSyncExternalStore (no setState-in-effect, SSR-safe).
 * The server snapshot (`false`) is only used while hydrating; the shell that uses this hook mounts after
 * the auth check resolves on the client, so the persisted value is the first one painted.
 */
export function useLocalStorageFlag(key: string): [boolean, (next: boolean) => void] {
  const subscribe = useCallback((cb: () => void) => {
    window.addEventListener("storage", cb);
    window.addEventListener(EVENT, cb);
    return () => {
      window.removeEventListener("storage", cb);
      window.removeEventListener(EVENT, cb);
    };
  }, []);
  const value = useSyncExternalStore(
    subscribe,
    () => read(key),
    () => false,
  );
  const set = useCallback(
    (next: boolean) => {
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      window.dispatchEvent(new Event(EVENT));
    },
    [key],
  );
  return [value, set];
}
