"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError } from "@/components/common/LoadError";
import { PickOne } from "@/components/common/PickOne";
import { useAction } from "@/hooks/useAction";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import type { Invitation, Role } from "@/lib/types";

/** Invite by email (member or admin — ownership is granted to members, never by invitation); pending ones can be revoked. */
export function InvitationsCard({ organizationId, onJoined }: { organizationId: string; owner: boolean; onJoined: () => void }) {
  const invitations = useLoader(() => api<Invitation[]>(`/organizations/${organizationId}/invitations`), [organizationId]);
  const { busy, act } = useAction();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await act(`Invited ${email.trim()}`, () => api<Invitation>(`/organizations/${organizationId}/invitations`, { method: "POST", body: { email: email.trim(), role } }), () => {
      invitations.reload();
      onJoined(); // an existing user joins at once
    });
    if (ok) setEmail("");
  };
  const revoke = (inv: Invitation) => act(`Invitation to ${inv.email} revoked`, () => api(`/organizations/${organizationId}/invitations/${inv.id}`, { method: "DELETE" }), invitations.reload);
  const pending = (invitations.data ?? []).filter((i) => i.status === "pending");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invitations</CardTitle>
        <CardDescription>An existing user joins the moment you invite them; a new one joins when they register with that email.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={invite} className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="invite-email">Email</Label>
            <Input id="invite-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="w-72" placeholder="colleague@company.com" />
          </div>
          <div className="space-y-1">
            <Label>Role</Label>
            <PickOne label="Invite as" value={role} items={{ member: "member", admin: "admin" }} onChange={(v) => setRole((v as Role) ?? "member")} className="w-32" />
          </div>
          <Button type="submit" disabled={busy || !email.trim()}>
            Invite
          </Button>
        </form>
        {invitations.error ? (
          <LoadError what="invitations" error={invitations.error} retry={invitations.reload} />
        ) : invitations.loading && !invitations.data ? (
          <Skeleton className="h-16 w-full" />
        ) : pending.length === 0 ? (
          <p className="text-sm text-muted-foreground">No pending invitations.</p>
        ) : (
          <Table aria-label="Pending invitations">
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Sent</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((inv) => (
                <TableRow key={inv.id} data-testid={`invitation-${inv.email}`}>
                  <TableCell>{inv.email}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{inv.role}</Badge>
                  </TableCell>
                  <TableCell>{when(inv.created_at)}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" disabled={busy} onClick={() => revoke(inv)}>
                      Revoke
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
