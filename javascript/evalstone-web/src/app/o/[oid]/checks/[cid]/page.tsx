import { AppShell } from "@/components/layout/AppShell";
import { CheckDetail } from "@/components/catalog/CheckDetail";

export default async function CheckDetailPage({ params }: { params: Promise<{ oid: string; cid: string }> }) {
  const { oid, cid } = await params;
  return (
    <AppShell organizationId={oid}>
      <CheckDetail checkId={cid} />
    </AppShell>
  );
}
