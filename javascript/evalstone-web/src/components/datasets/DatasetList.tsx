"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { TagChips } from "@/components/datasets/TagChips";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { when } from "@/lib/format";
import type { Dataset } from "@/lib/types";

/** The project's datasets. Content arrives as versions (pushed by the library or the API); here you name and tag them. */
export function DatasetList() {
  const router = useRouter();
  const { organization, project } = useWorkspace();
  const datasets = useLoader(() => api<Dataset[]>(`/projects/${project!.id}/datasets`), [project?.id]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const d = await api<Dataset>(`/projects/${project.id}/datasets`, {
        method: "POST",
        body: { name: name.trim(), description, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) },
      });
      toast.success(`Dataset "${d.name}" created`);
      setOpen(false);
      router.push(`${base}/datasets/${d.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Datasets"
        description="Named, tagged collections of samples; every push that changes the content becomes a new version."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name, href: base }, { label: "Datasets" }]}
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger render={<Button>New dataset</Button>} />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New dataset</DialogTitle>
              </DialogHeader>
              <form onSubmit={create} className="space-y-4">
                <div className="space-y-1">
                  <Label htmlFor="dataset-name">Name</Label>
                  <Input id="dataset-name" required value={name} onChange={(e) => setName(e.target.value)} autoFocus />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="dataset-description">Description</Label>
                  <Textarea id="dataset-description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="dataset-tags">Tags (comma-separated)</Label>
                  <Input id="dataset-tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="golden, regression" />
                </div>
                <Button type="submit" disabled={busy || !name.trim()}>
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        }
      />
      {datasets.error ? (
        <LoadError what="datasets" error={datasets.error} retry={datasets.reload} />
      ) : datasets.loading && !datasets.data ? (
        <Skeleton className="h-40 w-full" data-testid="loading" />
      ) : !datasets.data || datasets.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No datasets yet. Create one here, or push one from the library — a run that references a dataset creates it by content hash.
        </p>
      ) : (
        <Table aria-label="Datasets">
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Tags</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {datasets.data.map((d) => (
              <TableRow key={d.id}>
                <TableCell>
                  <Link href={`${base}/datasets/${d.id}`} className="font-medium underline-offset-4 hover:underline">
                    {d.name}
                  </Link>
                </TableCell>
                <TableCell className="max-w-md truncate text-muted-foreground">{d.description}</TableCell>
                <TableCell>
                  <TagChips tags={d.tags} />
                </TableCell>
                <TableCell>{when(d.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
