import { AppShell } from "@/components/layout/AppShell";
import { ProjectSettings } from "@/components/projects/ProjectSettings";

export default async function ProjectSettingsPage({ params }: { params: Promise<{ oid: string; pid: string }> }) {
  const { oid, pid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <ProjectSettings />
    </AppShell>
  );
}
