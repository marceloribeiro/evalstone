"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { MonitorForm } from "@/components/monitors/MonitorForm";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLiveEvent } from "@/contexts/WebSocketContext";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { pct, when } from "@/lib/format";
import { policyText } from "@/lib/monitoring";
import { isAdmin } from "@/lib/roles";
import type { Monitor } from "@/lib/types";

/** Monitors score a sample of the production traces the app pushes, every minute, with catalog checks. */
export function MonitorList() {
  const { organization, project } = useWorkspace();
  const monitors = useLoader(() => api<Monitor[]>(`/projects/${project!.id}/monitors`), [project?.id]);
  useLiveEvent("monitor.scored", () => monitors.reload());
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const admin = isAdmin(organization.role);

  return (
    <div>
      <PageHeader
        title="Monitors"
        description="Production traces (pushed with the project's ingest key) are sampled and scored on the beat with the organization's catalog checks; an alert opens when the window's metric drops below the threshold."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name, href: base }, { label: "Monitors" }]}
        actions={admin ? <MonitorForm organizationId={organization.id} projectId={project.id} base={base} /> : undefined}
      />
      {monitors.error ? (
        <LoadError what="monitors" error={monitors.error} retry={monitors.reload} />
      ) : monitors.loading && !monitors.data ? (
        <Skeleton className="h-40 w-full" data-testid="loading" />
      ) : !monitors.data?.length ? (
        <p className="text-sm text-muted-foreground">No monitors yet. {admin ? "Create one over the catalog checks the traces should pass." : "An admin creates them."}</p>
      ) : (
        <Table aria-label="Monitors">
          <TableHeader>
            <TableRow>
              <TableHead>Monitor</TableHead>
              <TableHead>Checks</TableHead>
              <TableHead>Sample</TableHead>
              <TableHead>Policy</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Last scored</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {monitors.data.map((m) => (
              <TableRow key={m.id} data-testid={`monitor-${m.name}`}>
                <TableCell>
                  <Link href={`${base}/monitors/${m.id}`} className="font-medium underline-offset-4 hover:underline">
                    {m.name}
                  </Link>
                </TableCell>
                <TableCell className="font-mono text-xs">{m.check_keys.join(", ")}</TableCell>
                <TableCell>{pct(m.sample_rate, 0)}</TableCell>
                <TableCell className="text-xs">{policyText(m.alert_policy)}</TableCell>
                <TableCell>
                  <Badge variant={m.status === "active" ? "default" : "secondary"}>{m.status}</Badge>
                  {m.last_error && <span className="ml-2 text-xs text-destructive">error</span>}
                </TableCell>
                <TableCell>{m.last_scored_at ? when(m.last_scored_at) : <span className="text-muted-foreground">never</span>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
