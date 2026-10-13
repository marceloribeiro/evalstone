"use client";

import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";

/** What a page shows when its loader failed: the API's message and a retry — never an empty state. */
export function LoadError({ what, error, retry }: { what: string; error: unknown; retry: () => void }) {
  return (
    <Alert variant="destructive" role="alert" data-testid="load-error">
      <AlertTitle>Could not load {what}</AlertTitle>
      <AlertDescription>{errorMessage(error)}</AlertDescription>
      <AlertAction>
        <Button variant="outline" size="sm" onClick={retry}>
          Retry
        </Button>
      </AlertAction>
    </Alert>
  );
}
