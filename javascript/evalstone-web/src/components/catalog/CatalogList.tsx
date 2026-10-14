"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { CheckForm } from "@/components/catalog/CheckForm";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { brief, when } from "@/lib/format";
import { isAdmin } from "@/lib/roles";
import { checksYaml } from "@/lib/yaml";
import type { BuiltinCheck, CatalogCheck } from "@/lib/types";

/** The organization's check catalog: what monitors score with and what the library pulls as `checks:`. */
export function CatalogList() {
  const router = useRouter();
  const { organization } = useWorkspace();
  const checks = useLoader(() => api<CatalogCheck[]>(`/organizations/${organization!.id}/checks`), [organization?.id]);
  const builtins = useLoader(() => api<BuiltinCheck[]>("/catalog/checks"), []);
  const yaml = useLoader(() => api<{ checks: Record<string, Record<string, unknown>> }>(`/organizations/${organization!.id}/checks/yaml`), [organization?.id, checks.data?.length]);
  if (!organization) return null;
  const admin = isAdmin(organization.role);
  const libraryVersion = builtins.data?.[0]?.library_version;

  return (
    <div>
      <PageHeader
        title="Check catalog"
        description={<>Checks defined once for the organization: monitors score traces with them, and an attached library pulls them as its <code>checks:</code> block.{libraryVersion && <> Built-in types from evalstone {libraryVersion}.</>}</>}
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: "Check catalog" }]}
        actions={admin && builtins.data ? <CheckForm organizationId={organization.id} builtins={builtins.data} trigger={<Button>New check</Button>} onSaved={(c) => router.push(`/o/${organization.id}/checks/${c.id}`)} /> : undefined}
      />
      <div className="space-y-6">
        {checks.error ? (
          <LoadError what="the catalog" error={checks.error} retry={checks.reload} />
        ) : checks.loading && !checks.data ? (
          <Skeleton className="h-40 w-full" data-testid="loading" />
        ) : !checks.data?.length ? (
          <p className="text-sm text-muted-foreground">No checks yet. {admin ? "Create the first one from a built-in type." : "An admin creates them."}</p>
        ) : (
          <Table aria-label="Checks">
            <TableHeader>
              <TableRow>
                <TableHead>Key</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Params</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {checks.data.map((c) => (
                <TableRow key={c.id} data-testid={`check-${c.key}`}>
                  <TableCell>
                    <Link href={`/o/${organization.id}/checks/${c.id}`} className="font-mono text-xs underline-offset-4 hover:underline">
                      {c.key}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{c.type}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{c.kind}</Badge>
                  </TableCell>
                  <TableCell className="max-w-md truncate font-mono text-xs text-muted-foreground">{brief(c.params, 90)}</TableCell>
                  <TableCell>v{c.current_version}</TableCell>
                  <TableCell>{when(c.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {yaml.data && Object.keys(yaml.data.checks).length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>As evalstone.yaml</CardTitle>
              <CardDescription>Paste this block into a project&apos;s evalstone.yaml, or let an attached library pull it.</CardDescription>
            </CardHeader>
            <CardContent>
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs" data-testid="checks-yaml">
                {checksYaml(yaml.data.checks)}
              </pre>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
