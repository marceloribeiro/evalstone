import { AppShell } from "@/components/layout/AppShell";
import { AlertList } from "@/components/alerts/AlertList";

export default async function AlertListPage({ params }: { params: Promise<{ oid: string; pid: string }> }) {
  const { oid, pid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <AlertList />
    </AppShell>
  );
}
