"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { WorkspaceProvider, useWorkspace } from "@/contexts/WorkspaceContext";
import { WebSocketProvider } from "@/contexts/WebSocketContext";
import { Sidebar } from "@/components/layout/Sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { RequireUser } from "@/components/auth/RequireUser";

/** Everything under /o/[oid] (and /o/[oid]/p/[pid]): signed in, org resolved, sidebar, main. */
export function AppShell({ organizationId, projectId, children }: { organizationId: string; projectId?: string; children: React.ReactNode }) {
  return (
    <RequireUser>
      {() => (
        <WorkspaceProvider key={organizationId} organizationId={organizationId} projectId={projectId}>
          <Gate projectId={projectId}>{children}</Gate>
        </WorkspaceProvider>
      )}
    </RequireUser>
  );
}

function Gate({ projectId, children }: { projectId?: string; children: React.ReactNode }) {
  const { organization, project, loading } = useWorkspace();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !organization) router.replace("/organizations");
    if (!loading && organization && projectId && !project) router.replace(`/o/${organization.id}`);
  }, [loading, organization, project, projectId, router]);
  if (loading) return <Skeleton className="m-8 h-40 w-full" data-testid="loading" />;
  if (!organization || (projectId && !project)) return null;
  const body = (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="min-w-0 flex-1 px-[30px] py-6">{children}</main>
    </div>
  );
  return projectId ? <WebSocketProvider projectId={projectId}>{body}</WebSocketProvider> : body;
}
