"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";

/**
 * One in-flight mutation at a time for a page: `act(label, fn, after?)` runs `fn`, toasts the
 * label on success (or the API's message on failure), calls `after` (typically the reloads) and
 * returns `fn`'s result — `null` when it failed — so callers that need the response share the
 * same busy flag instead of re-implementing the wrapper.
 */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const act = useCallback(async <T,>(label: string, fn: () => Promise<T>, after?: (result: T) => void): Promise<T | null> => {
    setBusy(true);
    try {
      const result = await fn();
      toast.success(label);
      after?.(result);
      return result;
    } catch (err) {
      toast.error(errorMessage(err));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, act };
}
