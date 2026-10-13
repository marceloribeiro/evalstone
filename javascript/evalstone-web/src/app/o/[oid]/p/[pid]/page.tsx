import { AppShell } from "@/components/layout/AppShell";
import { ProjectOverview } from "@/components/projects/ProjectOverview";

export default async function ProjectHome({ params }: { params: Promise<{ oid: string; pid: string }> }) {
  const { oid, pid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <ProjectOverview />
    </AppShell>
  );
}
