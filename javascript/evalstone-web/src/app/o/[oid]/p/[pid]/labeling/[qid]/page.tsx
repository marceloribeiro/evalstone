import { AppShell } from "@/components/layout/AppShell";
import { QueueDetail } from "@/components/labeling/QueueDetail";

export default async function QueuePage({ params }: { params: Promise<{ oid: string; pid: string; qid: string }> }) {
  const { oid, pid, qid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <QueueDetail queueId={qid} />
    </AppShell>
  );
}
