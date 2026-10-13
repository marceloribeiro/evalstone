"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { api, errorMessage } from "@/lib/api";
import type { Project } from "@/lib/types";

export function ProjectList() {
  const router = useRouter();
  const { organization, projects, reloadProjects } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  if (!organization) return null;

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const p = await api<Project>(`/organizations/${organization.id}/projects`, { method: "POST", body: { name } });
      toast.success(`Project "${p.name}" created`);
      setOpen(false);
      setName("");
      reloadProjects();
      router.push(`/o/${organization.id}/p/${p.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={organization.name}
        description="Projects in this organization."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name }]}
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger render={<Button>New project</Button>} />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New project</DialogTitle>
              </DialogHeader>
              <form onSubmit={create} className="space-y-4">
                <div className="space-y-1">
                  <Label htmlFor="project-name">Name</Label>
                  <Input id="project-name" required value={name} onChange={(e) => setName(e.target.value)} autoFocus />
                </div>
                <Button type="submit" disabled={busy || !name.trim()}>
                  Create
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        }
      />
      {projects.length ? (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Projects">
          {projects.map((p) => (
            <li key={p.id}>
              <Link href={`/o/${organization.id}/p/${p.id}`}>
                <Card className="transition-colors hover:bg-muted/40">
                  <CardHeader>
                    <CardTitle>{p.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">{p.description || p.slug}</CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">No projects yet. Create the first one.</p>
      )}
    </div>
  );
}
