"use client";

import { useCallback, useState } from "react";
import { useToast } from "@/components/Toaster";
import { getToken } from "./api";

/**
 * Wraps mutating (POST) calls: checks that an API token is set, surfaces
 * success/error toasts, tracks a pending flag, and calls `onDone` (e.g. to
 * refresh panels) after a successful action.
 */
export function useAction(onDone?: () => void) {
  const { push } = useToast();
  const [pending, setPending] = useState(false);

  const run = useCallback(
    async (fn: () => Promise<unknown>, successMsg?: string) => {
      if (!getToken()) {
        push("Set your API token in the header first.", "error");
        return false;
      }
      setPending(true);
      try {
        await fn();
        if (successMsg) push(successMsg, "success");
        onDone?.();
        return true;
      } catch (err) {
        push((err as Error)?.message || "Action failed", "error");
        return false;
      } finally {
        setPending(false);
      }
    },
    [onDone, push]
  );

  return { run, pending };
}
