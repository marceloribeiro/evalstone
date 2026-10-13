import { AppShell } from "@/components/layout/AppShell";
import { RunDetail } from "@/components/runs/RunDetail";

export default async function RunPage({ params }: { params: Promise<{ oid: string; pid: string; rid: string }> }) {
  const { oid, pid, rid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <RunDetail runId={rid} />
    </AppShell>
  );
}
