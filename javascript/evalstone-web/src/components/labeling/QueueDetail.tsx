"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { Pager } from "@/components/common/Pager";
import { KIND_LABEL } from "@/lib/labeling";
import { Stat } from "@/components/common/Stat";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { useAction } from "@/hooks/useAction";
import { when } from "@/lib/format";
import { isAdmin } from "@/lib/roles";
import type { LabelQueue, LabelTask, Member, Page, QueueProgress } from "@/lib/types";

const LIMIT = 50;

/** One queue: progress, instructions, the Label button, admin assignment + open/close, and the task list. */
export function QueueDetail({ queueId }: { queueId: string }) {
  const { organization, project } = useWorkspace();
  const queue = useLoader(() => api<LabelQueue>(`/projects/${project!.id}/label-queues/${queueId}`), [project?.id, queueId]);
  const progress = useLoader(() => api<QueueProgress>(`/projects/${project!.id}/label-queues/${queueId}/progress`), [project?.id, queueId]);
  const members = useLoader(() => api<Member[]>(`/organizations/${organization!.id}/members`), [organization?.id]);
  const [offset, setOffset] = useState(0);
  const tasks = useLoader(() => api<Page<LabelTask>>(`/projects/${project!.id}/label-queues/${queueId}/tasks`, { query: { offset, limit: LIMIT } }), [project?.id, queueId, offset]);
  const [picked, setPicked] = useState<string[]>([]);
  const { busy, act: run } = useAction();
  const [confirmUnassign, setConfirmUnassign] = useState(false);
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const admin = isAdmin(organization.role);
  const crumbs = [
    { label: "Home", href: "/organizations" },
    { label: organization.name, href: `/o/${organization.id}` },
    { label: project.name, href: base },
    { label: "Labeling", href: `${base}/labeling` },
    { label: queue.data?.name ?? "…" },
  ];
  if (!queue.data) {
    if (queue.loading) return <Skeleton className="h-40 w-full" data-testid="loading" />;
    return (
      <div>
        <PageHeader title="Queue" crumbs={crumbs} />
        <LoadError what="this queue" error={queue.error} retry={queue.reload} />
      </div>
    );
  }
  const q = queue.data;
  const p = progress.data;
  const email = (id: string | null) => (id ? (members.data?.find((m) => m.user.id === id)?.user.email ?? id.slice(0, 8)) : "—");
  const refresh = () => {
    queue.reload();
    progress.reload();
    tasks.reload();
  };

  const act = (label: string, fn: () => Promise<unknown>) =>
    run(label, fn, () => {
      setConfirmUnassign(false);
      refresh();
    });
  const setStatus = (status: "open" | "closed") => act(status === "open" ? "Queue reopened" : "Queue closed", () => api(`/projects/${project.id}/label-queues/${q.id}`, { method: "PATCH", body: { status } }));
  const assign = () => act(`Assigned to ${picked.length} member${picked.length === 1 ? "" : "s"}`, () => api(`/projects/${project.id}/label-queues/${q.id}/assign`, { method: "POST", body: { user_ids: picked } }));
  const unassign = () => act("Unassigned every pending task", () => api(`/projects/${project.id}/label-queues/${q.id}/unassign`, { method: "POST", body: { user_ids: null } }));

  return (
    <div>
      <PageHeader
        title={q.name}
        description={
          <>
            {KIND_LABEL[q.kind]} · label key <code className="text-xs">{q.kind === "compare" ? "compare:<run b>" : q.check_key || "overall"}</code>
            {q.kind !== "compare" && <> · scale {q.scale}</>} · created {when(q.created_at)}
          </>
        }
        crumbs={crumbs}
        actions={
          <>
            <Badge variant={q.status === "open" ? "default" : "secondary"}>{q.status}</Badge>
            {q.status === "open" && (p?.pending ?? 1) > 0 ? (
              <Button render={<Link href={`${base}/labeling/${q.id}/label`} />}>Label</Button>
            ) : (
              <Button disabled>Label</Button>
            )}
            {admin && (
              <Button variant="outline" disabled={busy} onClick={() => setStatus(q.status === "open" ? "closed" : "open")}>
                {q.status === "open" ? "Close queue" : "Reopen queue"}
              </Button>
            )}
          </>
        }
      />

      <dl className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5" aria-label="Progress">
        <Stat label="Tasks" value={p ? String(p.total) : "…"} />
        <Stat label="Pending" value={p ? String(p.pending - p.claimed) : "…"} />
        <Stat label="Claimed" value={p ? String(p.claimed) : "…"} />
        <Stat label="Done" value={p ? String(p.done) : "…"} />
        <Stat label="Skipped" value={p ? String(p.skipped) : "…"} />
      </dl>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Instructions</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm" data-testid="instructions">
              {q.instructions || <span className="text-muted-foreground">No instructions given.</span>}
            </p>
          </CardContent>
        </Card>
        {admin && (
          <Card>
            <CardHeader>
              <CardTitle>Assignment</CardTitle>
              <CardDescription>Pending tasks are dealt round-robin to the chosen members; unassigned tasks go to whoever labels next.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="grid gap-1 sm:grid-cols-2" aria-label="Members">
                {(members.data ?? []).map((m) => (
                  <li key={m.id}>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={picked.includes(m.user.id)}
                        onChange={(e) => setPicked(e.target.checked ? [...picked, m.user.id] : picked.filter((x) => x !== m.user.id))}
                      />
                      {m.user.email} <span className="text-xs text-muted-foreground">({m.role})</span>
                    </label>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <Button size="sm" disabled={busy || picked.length === 0 || q.status !== "open"} onClick={assign}>
                  Assign pending tasks
                </Button>
                <Dialog open={confirmUnassign} onOpenChange={setConfirmUnassign}>
                  <DialogTrigger render={<Button size="sm" variant="outline" disabled={busy}>Unassign all</Button>} />
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Unassign every pending task?</DialogTitle>
                      <DialogDescription>Claimed-but-unanswered tasks go back to the pool.</DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                      <Button variant="destructive" disabled={busy} onClick={unassign}>
                        Unassign
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Tasks</CardTitle>
        </CardHeader>
        <CardContent>
          {tasks.error ? (
            <LoadError what="the tasks" error={tasks.error} retry={tasks.reload} />
          ) : tasks.loading && !tasks.data ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <>
              <Table aria-label="Tasks" className={tasks.loading ? "opacity-60" : undefined} aria-busy={tasks.loading}>
                <TableHeader>
                  <TableRow>
                    <TableHead>#</TableHead>
                    <TableHead>Sample</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Assignee</TableHead>
                    <TableHead>Done</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tasks.data?.items.map((t) => (
                    <TableRow key={t.id}>
                      <TableCell>{t.position}</TableCell>
                      <TableCell className="font-mono text-xs">{t.sample_key}</TableCell>
                      <TableCell>
                        <Badge variant={t.status === "done" ? "default" : t.status === "skipped" ? "secondary" : "outline"}>{t.status}</Badge>
                        {t.payload.skip_reason && <span className="ml-2 text-xs text-muted-foreground">{t.payload.skip_reason}</span>}
                      </TableCell>
                      <TableCell className="text-xs">{email(t.assignee_user_id)}</TableCell>
                      <TableCell>{t.done_at ? when(t.done_at) : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Pager offset={offset} limit={LIMIT} total={tasks.data?.total ?? 0} onChange={setOffset} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
