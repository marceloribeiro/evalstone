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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { TagChips } from "@/components/datasets/TagChips";
import { SampleBrowser } from "@/components/datasets/SampleBrowser";
import { VersionDiff } from "@/components/datasets/VersionDiff";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { when } from "@/lib/format";
import type { Dataset, DatasetVersion } from "@/lib/types";

/** One dataset: its tags (admins edit), its versions, the samples of one version, and a diff between two. */
export function DatasetDetail({ datasetId }: { datasetId: string }) {
  const router = useRouter();
  const { organization, project } = useWorkspace();
  const dataset = useLoader(() => api<Dataset>(`/projects/${project!.id}/datasets/${datasetId}`), [project?.id, datasetId]);
  const versions = useLoader(() => api<DatasetVersion[]>(`/projects/${project!.id}/datasets/${datasetId}/versions`), [project?.id, datasetId]);
  const [chosen, setChosen] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const canEdit = organization.role === "admin" || organization.role === "owner";
  const crumbs = [
    { label: "Home", href: "/organizations" },
    { label: organization.name, href: `/o/${organization.id}` },
    { label: project.name, href: base },
    { label: "Datasets", href: `${base}/datasets` },
    { label: dataset.data?.name ?? "…" },
  ];
  if (!dataset.data) {
    if (dataset.loading) return <Skeleton className="h-40 w-full" data-testid="loading" />;
    return (
      <div>
        <PageHeader title="Dataset" crumbs={crumbs} />
        <LoadError what="this dataset" error={dataset.error} retry={dataset.reload} />
      </div>
    );
  }
  const d = dataset.data;
  const vs = versions.data ?? [];
  const latest = vs[vs.length - 1];
  const current = vs.find((v) => v.version === chosen) ?? latest;

  const setTags = async (tags: string[]) => {
    setBusy(true);
    try {
      await api(`/projects/${project.id}/datasets/${d.id}`, { method: "PATCH", body: { tags } });
      dataset.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await api(`/projects/${project.id}/datasets/${d.id}`, { method: "DELETE" });
      toast.success(`Dataset "${d.name}" deleted`);
      router.push(`${base}/datasets`);
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={d.name}
        description={d.description || "No description."}
        crumbs={crumbs}
        actions={
          canEdit ? (
            <Dialog>
              <DialogTrigger render={<Button variant="outline" size="sm">Delete dataset</Button>} />
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete &quot;{d.name}&quot;?</DialogTitle>
                  <DialogDescription>Runs that referenced its versions keep their link; the dataset disappears from this list.</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button variant="destructive" disabled={busy} onClick={remove}>
                    Delete
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          ) : undefined
        }
      />
      <div className="mb-6">
        <TagChips tags={d.tags} onChange={canEdit ? setTags : undefined} busy={busy} />
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Versions</CardTitle>
          <CardDescription>Immutable snapshots; the hash is the library&apos;s content hash, so a run&apos;s report links to the exact version it ran on.</CardDescription>
        </CardHeader>
        <CardContent>
          {versions.error ? (
            <LoadError what="the versions" error={versions.error} retry={versions.reload} />
          ) : versions.loading && !versions.data ? (
            <Skeleton className="h-20 w-full" />
          ) : vs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No versions yet. Push samples with the library, or POST them to this dataset&apos;s versions endpoint.</p>
          ) : (
            <Table aria-label="Versions">
              <TableHeader>
                <TableRow>
                  <TableHead>Version</TableHead>
                  <TableHead>Samples</TableHead>
                  <TableHead>Content hash</TableHead>
                  <TableHead>Note</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...vs].reverse().map((v) => (
                  <TableRow key={v.id} data-state={current?.id === v.id ? "selected" : undefined} className="cursor-pointer" onClick={() => setChosen(v.version)}>
                    <TableCell>
                      <Button variant={current?.id === v.id ? "default" : "ghost"} size="sm" aria-pressed={current?.id === v.id}>
                        v{v.version}
                      </Button>
                      {v.id === latest?.id && (
                        <Badge variant="secondary" className="ml-2">
                          latest
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>{v.sample_count}</TableCell>
                    <TableCell className="font-mono text-xs">{v.content_hash.slice(0, 12)}</TableCell>
                    <TableCell className="max-w-md truncate text-muted-foreground">{v.note}</TableCell>
                    <TableCell>{when(v.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {current && (
        <Tabs defaultValue="samples">
          <TabsList>
            <TabsTrigger value="samples">Samples of v{current.version}</TabsTrigger>
            <TabsTrigger value="diff">Diff</TabsTrigger>
          </TabsList>
          <TabsContent value="samples">
            <SampleBrowser projectId={project.id} datasetId={d.id} version={current} />
          </TabsContent>
          <TabsContent value="diff">
            <VersionDiff projectId={project.id} datasetId={d.id} versions={vs} to={current} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
