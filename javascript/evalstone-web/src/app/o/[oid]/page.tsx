import { AppShell } from "@/components/layout/AppShell";
import { ProjectList } from "@/components/projects/ProjectList";

export default async function OrganizationHome({ params }: { params: Promise<{ oid: string }> }) {
  const { oid } = await params;
  return (
    <AppShell organizationId={oid}>
      <ProjectList />
    </AppShell>
  );
}
