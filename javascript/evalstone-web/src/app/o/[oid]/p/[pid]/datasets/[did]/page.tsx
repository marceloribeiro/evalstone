import { AppShell } from "@/components/layout/AppShell";
import { DatasetDetail } from "@/components/datasets/DatasetDetail";

export default async function DatasetPage({ params }: { params: Promise<{ oid: string; pid: string; did: string }> }) {
  const { oid, pid, did } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <DatasetDetail datasetId={did} />
    </AppShell>
  );
}
