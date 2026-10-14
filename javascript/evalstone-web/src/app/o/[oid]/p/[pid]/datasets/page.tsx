import { AppShell } from "@/components/layout/AppShell";
import { DatasetList } from "@/components/datasets/DatasetList";

export default async function DatasetsPage({ params }: { params: Promise<{ oid: string; pid: string }> }) {
  const { oid, pid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <DatasetList />
    </AppShell>
  );
}
