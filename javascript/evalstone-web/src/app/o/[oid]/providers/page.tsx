import { AppShell } from "@/components/layout/AppShell";
import { ProviderList } from "@/components/providers/ProviderList";

export default async function ProvidersPage({ params }: { params: Promise<{ oid: string }> }) {
  const { oid } = await params;
  return (
    <AppShell organizationId={oid}>
      <ProviderList />
    </AppShell>
  );
}
