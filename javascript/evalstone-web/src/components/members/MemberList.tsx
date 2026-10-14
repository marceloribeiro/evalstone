"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { PickOne } from "@/components/common/PickOne";
import { InvitationsCard } from "@/components/members/InvitationsCard";
import { useAuth } from "@/contexts/AuthContext";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useAction } from "@/hooks/useAction";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { isAdmin, roleAtLeast } from "@/lib/roles";
import type { Member, Role } from "@/lib/types";

const ROLE_LABEL: Record<Role, string> = { member: "member", admin: "admin", owner: "owner" };

/** Who is in the organization and what they may do; admins change roles and remove, owners alone grant or revoke ownership. */
export function MemberList() {
  const { organization } = useWorkspace();
  const { user } = useAuth();
  const members = useLoader(() => api<Member[]>(`/organizations/${organization!.id}/members`), [organization?.id]);
  const { busy, act } = useAction();
  const [removing, setRemoving] = useState<Member | null>(null);
  if (!organization) return null;
  const admin = isAdmin(organization.role);
  const owner = roleAtLeast(organization.role, "owner");
  // an admin may move people between member and admin; only an owner touches ownership
  const roleItems: Record<string, string> = owner ? ROLE_LABEL : { member: "member", admin: "admin" };

  const setRole = (m: Member, role: Role) =>
    act(`${m.user.email} is now ${ROLE_LABEL[role]}`, () => api(`/organizations/${organization.id}/members/${m.id}`, { method: "PATCH", body: { role } }), members.reload);
  const remove = (m: Member) =>
    act(`${m.user.email} removed`, () => api(`/organizations/${organization.id}/members/${m.id}`, { method: "DELETE" }), () => {
      setRemoving(null);
      members.reload();
    });

  return (
    <div>
      <PageHeader
        title="Members"
        description="Members read everything in the organization; admins change settings, catalog, providers and queues; owners manage ownership and the organization itself."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: "Members" }]}
      />
      <div className="space-y-6">
        {members.error ? (
          <LoadError what="members" error={members.error} retry={members.reload} />
        ) : members.loading && !members.data ? (
          <Skeleton className="h-40 w-full" data-testid="loading" />
        ) : (
          <Table aria-label="Members">
            <TableHeader>
              <TableRow>
                <TableHead>Member</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Since</TableHead>
                {admin && <TableHead />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.data?.map((m) => {
                const self = m.user.id === user?.id;
                const canEdit = admin && (owner || m.role !== "owner"); // an admin cannot touch an owner's row
                return (
                  <TableRow key={m.id} data-testid={`member-${m.user.email}`}>
                    <TableCell className="font-medium">
                      {m.user.email}
                      {self && (
                        <Badge variant="outline" className="ml-2">
                          you
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {m.user.first_name} {m.user.last_name}
                    </TableCell>
                    <TableCell>
                      {canEdit ? (
                        <PickOne label={`Role of ${m.user.email}`} value={m.role} items={roleItems} onChange={(v) => v && v !== m.role && setRole(m, v as Role)} className="w-32" />
                      ) : (
                        <Badge variant={m.role === "owner" ? "default" : "secondary"}>{m.role}</Badge>
                      )}
                    </TableCell>
                    <TableCell>{when(m.created_at)}</TableCell>
                    {admin && (
                      <TableCell className="text-right">
                        {canEdit && (
                          <Button size="sm" variant="outline" disabled={busy} onClick={() => setRemoving(m)}>
                            Remove
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        {admin && <InvitationsCard organizationId={organization.id} owner={owner} onJoined={members.reload} />}
      </div>
      <Dialog open={!!removing} onOpenChange={(o) => !o && setRemoving(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove {removing?.user.email}?</DialogTitle>
            <DialogDescription>They lose access to every project of the organization. Labels and runs they created stay.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="destructive" disabled={busy} onClick={() => removing && remove(removing)}>
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

