import { AppShell } from "@/components/layout/AppShell";
import { CatalogList } from "@/components/catalog/CatalogList";

export default async function CatalogListPage({ params }: { params: Promise<{ oid: string }> }) {
  const { oid } = await params;
  return (
    <AppShell organizationId={oid}>
      <CatalogList />
    </AppShell>
  );
}
