import { AppShell } from "@/components/layout/AppShell";
import { MemberList } from "@/components/members/MemberList";

export default async function MembersPage({ params }: { params: Promise<{ oid: string }> }) {
  const { oid } = await params;
  return (
    <AppShell organizationId={oid}>
      <MemberList />
    </AppShell>
  );
}
