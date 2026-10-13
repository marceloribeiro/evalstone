import { AppShell } from "@/components/layout/AppShell";
import { RunList } from "@/components/runs/RunList";

export default async function RunsPage({ params }: { params: Promise<{ oid: string; pid: string }> }) {
  const { oid, pid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <RunList />
    </AppShell>
  );
}
