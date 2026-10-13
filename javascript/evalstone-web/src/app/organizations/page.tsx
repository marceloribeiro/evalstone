"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { OrganizationList } from "@/components/organizations/OrganizationList";
import { Skeleton } from "@/components/ui/skeleton";
import { Brand } from "@/components/layout/Brand";
import { Button } from "@/components/ui/button";

export default function OrganizationsPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);
  if (loading) return <Skeleton className="m-8 h-40 w-full" data-testid="loading" />;
  if (!user) return null;
  return (
    <div className="min-h-screen">
      <header className="flex h-14 items-center justify-between border-b px-[30px]">
        <Brand />
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span>{user.email}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              logout();
              router.replace("/login");
            }}
          >
            Sign out
          </Button>
        </div>
      </header>
      <main className="px-[30px] py-6">
        <OrganizationList />
      </main>
    </div>
  );
}
