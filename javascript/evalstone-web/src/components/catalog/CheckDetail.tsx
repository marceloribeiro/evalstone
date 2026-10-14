"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { CheckForm } from "@/components/catalog/CheckForm";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { when } from "@/lib/format";
import { isAdmin } from "@/lib/roles";
import { toYaml } from "@/lib/yaml";
import type { BuiltinCheck, CatalogCheck, CheckVersion } from "@/lib/types";

/** One catalog check: its current params, the built-in type's summary, every version, edit (new version on content change) and delete. */
export function CheckDetail({ checkId }: { checkId: string }) {
  const router = useRouter();
  const { organization } = useWorkspace();
  const check = useLoader(() => api<CatalogCheck>(`/organizations/${organization!.id}/checks/${checkId}`), [organization?.id, checkId]);
  const versions = useLoader(() => api<CheckVersion[]>(`/organizations/${organization!.id}/checks/${checkId}/versions`), [organization?.id, checkId, check.data?.current_version]);
  const builtins = useLoader(() => api<BuiltinCheck[]>("/catalog/checks"), []);
  const [deleting, setDeleting] = useState(false);
  if (!organization) return null;
  const admin = isAdmin(organization.role);
  const crumbs = [
    { label: "Home", href: "/organizations" },
    { label: organization.name, href: `/o/${organization.id}` },
    { label: "Check catalog", href: `/o/${organization.id}/checks` },
    { label: check.data?.key ?? "…" },
  ];
  if (!check.data) {
    if (check.loading) return <Skeleton className="h-40 w-full" data-testid="loading" />;
    return (
      <div>
        <PageHeader title="Check" crumbs={crumbs} />
        <LoadError what="this check" error={check.error} retry={check.reload} />
      </div>
    );
  }
  const c = check.data;
  const builtin = builtins.data?.find((b) => b.type === c.type);
  const remove = async () => {
    setDeleting(true);
    try {
      await api(`/organizations/${organization.id}/checks/${c.id}`, { method: "DELETE" });
      toast.success(`Check "${c.key}" deleted`);
      router.push(`/o/${organization.id}/checks`);
    } catch (err) {
      toast.error(errorMessage(err));
      setDeleting(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={c.key}
        description={
          <>
            <code className="text-xs">{c.type}</code> · <Badge variant="outline">{c.kind}</Badge> · version {c.current_version} · updated {when(c.updated_at)}
          </>
        }
        crumbs={crumbs}
        actions={
          admin && builtins.data ? (
            <>
              <CheckForm organizationId={organization.id} builtins={builtins.data} existing={c} trigger={<Button variant="outline" size="sm">Edit</Button>} onSaved={() => check.reload()} />
              <Dialog>
                <DialogTrigger render={<Button variant="outline" size="sm" disabled={deleting}>Delete</Button>} />
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Delete &quot;{c.key}&quot;?</DialogTitle>
                    <DialogDescription>Monitors that reference it stop scoring with it; stored results keep their check key.</DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="destructive" disabled={deleting} onClick={remove}>
                      Delete
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </>
          ) : undefined
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Params</CardTitle>
            {builtin && <CardDescription>{builtin.summary}</CardDescription>}
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs" data-testid="check-params">
              {`${c.key}:\n  type: ${c.type}${toYaml(c.params, 1)}`}
            </pre>
            <p className="mt-3 text-sm" data-testid="check-description">
              {c.description || <span className="text-muted-foreground">No description.</span>}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Versions</CardTitle>
            <CardDescription>Every type/params change is a new version; results and monitors refer to the content hash.</CardDescription>
          </CardHeader>
          <CardContent>
            {versions.error ? (
              <LoadError what="the versions" error={versions.error} retry={versions.reload} />
            ) : !versions.data ? (
              <Skeleton className="h-20 w-full" />
            ) : (
              <Table aria-label="Versions">
                <TableHeader>
                  <TableRow>
                    <TableHead>Version</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Hash</TableHead>
                    <TableHead>Note</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...versions.data].reverse().map((v) => (
                    <TableRow key={v.id} data-testid={`version-${v.version}`}>
                      <TableCell>
                        v{v.version}
                        {v.version === c.current_version && (
                          <Badge variant="secondary" className="ml-2">
                            current
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{v.type}</TableCell>
                      <TableCell className="font-mono text-xs">{v.content_hash.slice(0, 12)}</TableCell>
                      <TableCell className="max-w-xs truncate text-muted-foreground">{v.note}</TableCell>
                      <TableCell>{when(v.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
