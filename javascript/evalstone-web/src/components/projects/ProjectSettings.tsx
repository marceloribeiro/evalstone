"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { MintKeyForm } from "@/components/projects/MintKeyForm";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useAction } from "@/hooks/useAction";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { when } from "@/lib/format";
import { isAdmin } from "@/lib/roles";
import type { IngestKey, Project } from "@/lib/types";

/** Project name / slug / description, the ingest keys (mint, revoke), and deletion — admins only; members read. */
export function ProjectSettings() {
  const router = useRouter();
  const { organization, project, reloadProjects } = useWorkspace();
  const admin = isAdmin(organization?.role);
  const keys = useLoader(() => (admin ? api<IngestKey[]>(`/projects/${project!.id}/ingest-keys`) : Promise.resolve([] as IngestKey[])), [project?.id, admin]);
  const { busy, act } = useAction();
  const [name, setName] = useState<string | null>(null);
  const [slug, setSlug] = useState<string | null>(null);
  const [description, setDescription] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const form = { name: name ?? project.name, slug: slug ?? project.slug, description: description ?? project.description };
  const dirty = form.name !== project.name || form.slug !== project.slug || form.description !== project.description;

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    act("Project saved", () => api<Project>(`/projects/${project.id}`, { method: "PATCH", body: { name: form.name.trim(), slug: form.slug.trim(), description: form.description } }), (saved) => {
      // the form shows what the API stored (slug may be normalised) until the workspace catches up
      setName(saved.name);
      setSlug(saved.slug);
      setDescription(saved.description);
      reloadProjects(); // the header and the sidebar switcher read the project from there
    });
  };
  const revoke = (k: IngestKey) => act(`Key "${k.name}" revoked`, () => api(`/projects/${project.id}/ingest-keys/${k.id}`, { method: "DELETE" }), keys.reload);
  const remove = async () => {
    setDeleting(true);
    try {
      await api(`/projects/${project.id}`, { method: "DELETE" });
      toast.success(`Project "${project.name}" deleted`);
      router.push(`/o/${organization.id}`); // the organization page mounts its own workspace and refetches
    } catch (err) {
      toast.error(errorMessage(err));
      setDeleting(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Settings"
        description={admin ? "Name, slug and description; the ingest keys the library and your app authenticate with; deletion." : "Project settings are edited by organization admins."}
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name, href: base }, { label: "Settings" }]}
      />
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Project</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={save} className="max-w-xl space-y-3" aria-label="Project form">
              <div className="space-y-1">
                <Label htmlFor="project-name">Name</Label>
                <Input id="project-name" value={form.name} disabled={!admin} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="project-slug">Slug</Label>
                <Input id="project-slug" value={form.slug} disabled={!admin} onChange={(e) => setSlug(e.target.value)} className="font-mono" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="project-description">Description</Label>
                <Textarea id="project-description" rows={2} value={form.description} disabled={!admin} onChange={(e) => setDescription(e.target.value)} />
              </div>
              {admin && (
                <Button type="submit" disabled={busy || !dirty || !form.name.trim() || !form.slug.trim()}>
                  Save
                </Button>
              )}
            </form>
          </CardContent>
        </Card>

        {admin && (
          <Card>
            <CardHeader>
              <CardTitle>Ingest keys</CardTitle>
              <CardDescription>What `evalstone run` and your app send as the bearer. A key is shown once; revoke one to rotate.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <MintKeyForm projectId={project.id} onMinted={() => keys.reload()} />
              {keys.error ? (
                <LoadError what="the ingest keys" error={keys.error} retry={keys.reload} />
              ) : (
                <Table aria-label="Ingest keys">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Prefix</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Last used</TableHead>
                      <TableHead>State</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {keys.data?.map((k) => (
                      <TableRow key={k.id} data-testid={`key-${k.name}`}>
                        <TableCell>{k.name}</TableCell>
                        <TableCell className="font-mono text-xs">{k.prefix}…</TableCell>
                        <TableCell>{when(k.created_at)}</TableCell>
                        <TableCell>{k.last_used_at ? when(k.last_used_at) : "never"}</TableCell>
                        <TableCell>{k.revoked_at ? <Badge variant="secondary">revoked</Badge> : <Badge>active</Badge>}</TableCell>
                        <TableCell className="text-right">
                          {!k.revoked_at && (
                            <Button size="sm" variant="outline" disabled={busy} onClick={() => revoke(k)}>
                              Revoke
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                    {keys.data && keys.data.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={6} className="text-muted-foreground">
                          No keys yet.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        )}

        {admin && (
          <Card>
            <CardHeader>
              <CardTitle>Danger zone</CardTitle>
              <CardDescription>Deleting the project hides it and everything under it (runs, datasets, queues, monitors); ingest keys stop working.</CardDescription>
            </CardHeader>
            <CardContent>
              <Dialog>
                <DialogTrigger render={<Button variant="destructive" disabled={busy || deleting}>Delete project</Button>} />
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Delete &quot;{project.name}&quot;?</DialogTitle>
                    <DialogDescription>This cannot be undone from the app.</DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="destructive" disabled={deleting} onClick={remove}>
                      Delete project
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
