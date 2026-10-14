import { AppShell } from "@/components/layout/AppShell";
import { MonitorDetail } from "@/components/monitors/MonitorDetail";

export default async function MonitorDetailPage({ params }: { params: Promise<{ oid: string; pid: string; mid: string }> }) {
  const { oid, pid, mid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <MonitorDetail monitorId={mid} />
    </AppShell>
  );
}
