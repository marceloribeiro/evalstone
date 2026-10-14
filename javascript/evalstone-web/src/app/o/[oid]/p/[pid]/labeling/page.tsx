import { AppShell } from "@/components/layout/AppShell";
import { QueueList } from "@/components/labeling/QueueList";

export default async function LabelingPage({ params }: { params: Promise<{ oid: string; pid: string }> }) {
  const { oid, pid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <QueueList />
    </AppShell>
  );
}
