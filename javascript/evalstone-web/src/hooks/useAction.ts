"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";

/**
 * One in-flight mutation at a time for a page: `act(label, fn, after?)` runs `fn`, toasts the
 * label on success (or the API's message on failure) and calls `after` (typically the reloads).
 */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const act = useCallback(async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    setBusy(true);
    try {
      await fn();
      toast.success(label);
      after?.();
      return true;
    } catch (err) {
      toast.error(errorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, act };
}
