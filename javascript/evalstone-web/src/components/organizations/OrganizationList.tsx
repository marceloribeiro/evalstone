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
import { Skeleton } from "@/components/ui/skeleton";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import type { Organization } from "@/lib/types";
import { rememberOrganization } from "@/contexts/WorkspaceContext";

export function OrganizationList() {
  const router = useRouter();
  const { data, loading, reload } = useLoader(() => api<Organization[]>("/organizations"), []);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const org = await api<Organization>("/organizations", { method: "POST", body: { name } });
      toast.success(`Organization "${org.name}" created`);
      setOpen(false);
      setName("");
      rememberOrganization(org.id);
      reload();
      router.push(`/o/${org.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Organizations</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger render={<Button>New organization</Button>} />
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New organization</DialogTitle>
            </DialogHeader>
            <form onSubmit={create} className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="org-name">Name</Label>
                <Input id="org-name" required value={name} onChange={(e) => setName(e.target.value)} autoFocus />
              </div>
              <Button type="submit" disabled={busy || !name.trim()}>
                Create
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>
      {loading ? (
        <Skeleton className="h-24 w-full" data-testid="loading" />
      ) : data && data.length ? (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Organizations">
          {data.map((org) => (
            <li key={org.id}>
              <Link href={`/o/${org.id}`} onClick={() => rememberOrganization(org.id)}>
                <Card className="transition-colors hover:bg-muted/40">
                  <CardHeader>
                    <CardTitle>{org.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">{org.website_url ?? "Open"}</CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">You are not in an organization yet. Create one to start.</p>
      )}
    </div>
  );
}
