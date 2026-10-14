"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { Stat } from "@/components/common/Stat";
import { AlertTable } from "@/components/alerts/AlertTable";
import { TraceTable } from "@/components/monitors/TraceTable";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLiveEvent } from "@/contexts/WebSocketContext";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { pct, when } from "@/lib/format";
import { metricValue, policyText } from "@/lib/monitoring";
import { isAdmin } from "@/lib/roles";
import type { Alert, Monitor, MonitorWindow } from "@/lib/types";

/** One monitor: the window the policy sees right now, its alerts, the recent traces; admins pause/resume, score now, delete. */
export function MonitorDetail({ monitorId }: { monitorId: string }) {
  const router = useRouter();
  const { organization, project } = useWorkspace();
  const monitor = useLoader(() => api<Monitor>(`/projects/${project!.id}/monitors/${monitorId}`), [project?.id, monitorId]);
  const window = useLoader(() => api<MonitorWindow>(`/projects/${project!.id}/monitors/${monitorId}/window`), [project?.id, monitorId]);
  const alerts = useLoader(() => api<Alert[]>(`/projects/${project!.id}/alerts`).then((all) => all.filter((a) => a.monitor_id === monitorId)), [project?.id, monitorId]);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const refresh = () => {
    monitor.reload();
    window.reload();
    alerts.reload();
  };
  useLiveEvent("monitor.scored", (e) => e.monitor_id === monitorId && refresh());
  useLiveEvent("alert.opened", (e) => e.monitor_id === monitorId && refresh());
  useLiveEvent("alert.resolved", (e) => e.monitor_id === monitorId && refresh());
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const admin = isAdmin(organization.role);
  const crumbs = [
    { label: "Home", href: "/organizations" },
    { label: organization.name, href: `/o/${organization.id}` },
    { label: project.name, href: base },
    { label: "Monitors", href: `${base}/monitors` },
    { label: monitor.data?.name ?? "…" },
  ];
  if (!monitor.data) {
    if (monitor.loading) return <Skeleton className="h-40 w-full" data-testid="loading" />;
    return (
      <div>
        <PageHeader title="Monitor" crumbs={crumbs} />
        <LoadError what="this monitor" error={monitor.error} retry={monitor.reload} />
      </div>
    );
  }
  const m = monitor.data;
  const w = window.data;
  const metric = m.alert_policy.metric;
  const current = w ? (metric === "pass_rate" ? w.pass_rate : w.mean_score) : null;
  const below = current != null && current < m.alert_policy.threshold;
  const openAlert = alerts.data?.find((a) => !a.resolved_at);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      toast.success(label);
      refresh();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const setStatus = (status: "active" | "paused") => act(status === "paused" ? "Monitor paused (open alerts resolved)" : "Monitor resumed", () => api(`/projects/${project.id}/monitors/${m.id}`, { method: "PATCH", body: { status } }));
  const scoreNow = () => act("Scoring pass enqueued", () => api(`/projects/${project.id}/monitors/${m.id}/score`, { method: "POST" }));
  const remove = async () => {
    setBusy(true);
    try {
      await api(`/projects/${project.id}/monitors/${m.id}`, { method: "DELETE" });
      toast.success(`Monitor "${m.name}" deleted`);
      router.push(`${base}/monitors`);
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={m.name}
        description={
          <>
            Checks <code className="text-xs">{m.check_keys.join(", ")}</code> · sample {pct(m.sample_rate, 0)} · {policyText(m.alert_policy)}
            {m.webhook_url && <> · webhook set</>}
          </>
        }
        crumbs={crumbs}
        actions={
          <>
            <Badge variant={m.status === "active" ? "default" : "secondary"} data-testid="monitor-status">
              {m.status}
            </Badge>
            {admin && (
              <>
                <Button variant="outline" size="sm" disabled={busy} onClick={scoreNow}>
                  Score now
                </Button>
                <Button variant="outline" size="sm" disabled={busy} onClick={() => setStatus(m.status === "active" ? "paused" : "active")}>
                  {m.status === "active" ? "Pause" : "Resume"}
                </Button>
                <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
                  <DialogTrigger render={<Button variant="outline" size="sm" disabled={busy}>Delete</Button>} />
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Delete monitor &quot;{m.name}&quot;?</DialogTitle>
                      <DialogDescription>Its open alerts are resolved; the traces stay.</DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                      <Button variant="destructive" disabled={busy} onClick={remove}>
                        Delete
                      </Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </>
            )}
          </>
        }
      />
      {m.last_error && (
        <p className="mb-4 text-sm text-destructive" data-testid="monitor-error">
          Last scoring error: {m.last_error}
        </p>
      )}
      <dl className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Window">
        <Stat label={`Traces in the last ${w?.window_minutes ?? m.alert_policy.window_minutes} min`} value={w ? String(w.n) : "…"} />
        <Stat label="Pass rate" value={w?.pass_rate == null ? "—" : pct(w.pass_rate)} warn={metric === "pass_rate" && below} />
        <Stat label="Mean score" value={w?.mean_score == null ? "—" : w.mean_score.toFixed(3)} warn={metric === "mean_score" && below} />
        <Stat label="Alert" value={openAlert ? `open · ${metricValue(openAlert.metric, openAlert.value)}` : "none"} warn={!!openAlert} />
      </dl>
      <p className="mb-6 text-xs text-muted-foreground">
        Last scored {m.last_scored_at ? when(m.last_scored_at) : "never"} · the beat scores active monitors every minute; Score now enqueues a pass immediately.
      </p>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Alerts</CardTitle>
            <CardDescription>Opened when the window&apos;s metric fell below the threshold with at least the minimum traces; resolved as soon as it recovers.</CardDescription>
          </CardHeader>
          <CardContent>{alerts.error ? <LoadError what="the alerts" error={alerts.error} retry={alerts.reload} /> : <AlertTable alerts={alerts.data ?? []} monitors={{ [m.id]: m.name }} loading={alerts.loading && !alerts.data} />}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Recent traces</CardTitle>
            <CardDescription>Newest first, every trace the app pushed (sampled or not). Flag one to find it again.</CardDescription>
          </CardHeader>
          <CardContent>
            <TraceTable projectId={project.id} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
