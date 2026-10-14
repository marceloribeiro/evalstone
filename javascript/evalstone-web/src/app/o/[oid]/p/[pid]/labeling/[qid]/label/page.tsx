import { AppShell } from "@/components/layout/AppShell";
import { Labeler } from "@/components/labeling/Labeler";

export default async function LabelPage({ params }: { params: Promise<{ oid: string; pid: string; qid: string }> }) {
  const { oid, pid, qid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <Labeler queueId={qid} />
    </AppShell>
  );
}
