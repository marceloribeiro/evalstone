import { AppShell } from "@/components/layout/AppShell";
import { MonitorList } from "@/components/monitors/MonitorList";

export default async function MonitorListPage({ params }: { params: Promise<{ oid: string; pid: string }> }) {
  const { oid, pid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <MonitorList />
    </AppShell>
  );
}
