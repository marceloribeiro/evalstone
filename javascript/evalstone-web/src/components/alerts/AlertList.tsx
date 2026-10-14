"use client";

import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { AlertTable } from "@/components/alerts/AlertTable";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLiveEvent } from "@/contexts/WebSocketContext";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import type { Alert, Monitor } from "@/lib/types";

/** Every alert of the project, open first, live on alert.opened / alert.resolved. */
export function AlertList() {
  const { organization, project } = useWorkspace();
  const alerts = useLoader(() => api<Alert[]>(`/projects/${project!.id}/alerts`), [project?.id]);
  const monitors = useLoader(() => api<Monitor[]>(`/projects/${project!.id}/monitors`), [project?.id]);
  useLiveEvent("alert.opened", () => alerts.reload());
  useLiveEvent("alert.resolved", () => alerts.reload());
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const open = alerts.data?.filter((a) => !a.resolved_at).length ?? 0;
  const names = Object.fromEntries((monitors.data ?? []).map((m) => [m.id, m.name]));
  return (
    <div>
      <PageHeader
        title="Alerts"
        description={alerts.data ? `${open} open · ${alerts.data.length - open} resolved` : "Policy breaches across the project's monitors."}
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name, href: base }, { label: "Alerts" }]}
      />
      {alerts.error ? <LoadError what="alerts" error={alerts.error} retry={alerts.reload} /> : <AlertTable alerts={alerts.data ?? []} monitors={names} loading={alerts.loading && !alerts.data} base={base} />}
    </div>
  );
}
