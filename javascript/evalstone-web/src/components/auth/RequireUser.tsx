"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

/**
 * The signed-in gate for every app page: a skeleton while `/me` is in flight, a retry panel when
 * the center could not be reached (the token is kept), `/login` when there is no session.
 */
export function RequireUser({ children }: { children: (user: NonNullable<ReturnType<typeof useAuth>["user"]>) => React.ReactNode }) {
  const { user, loading, unreachable, retry } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user && !unreachable) router.replace("/login");
  }, [loading, user, unreachable, router]);
  if (loading) return <Skeleton className="m-8 h-40 w-full" data-testid="loading" />;
  if (!user && unreachable) {
    return (
      <main className="m-8 max-w-md space-y-3">
        <div role="alert">
          <p className="font-medium">The center is not reachable right now.</p>
          <p className="text-sm text-muted-foreground">Your session was kept. Try again in a moment.</p>
        </div>
        <Button onClick={retry}>Retry</Button>
      </main>
    );
  }
  if (!user) return null;
  return <>{children(user)}</>;
}
