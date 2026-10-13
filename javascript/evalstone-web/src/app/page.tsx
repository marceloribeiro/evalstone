"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { lastOrganization } from "@/contexts/WorkspaceContext";
import { Skeleton } from "@/components/ui/skeleton";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
    else {
      const last = lastOrganization();
      router.replace(last ? `/o/${last}` : "/organizations");
    }
  }, [loading, user, router]);
  return <Skeleton className="m-8 h-40 w-full" />;
}
