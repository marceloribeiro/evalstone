import { AppShell } from "@/components/layout/AppShell";
import { Judges } from "@/components/judges/Judges";

export default async function JudgesPage({ params }: { params: Promise<{ oid: string; pid: string }> }) {
  const { oid, pid } = await params;
  return (
    <AppShell organizationId={oid} projectId={pid}>
      <Judges />
    </AppShell>
  );
}
