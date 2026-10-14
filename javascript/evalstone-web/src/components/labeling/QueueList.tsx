"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { QueueForm } from "@/components/labeling/QueueForm";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { isAdmin } from "@/lib/roles";
import type { LabelQueue } from "@/lib/types";

export const KIND_LABEL: Record<LabelQueue["kind"], string> = { grade: "Grade outputs", compare: "A/B compare", verify: "Verify dataset" };

/** The project's labeling queues; admins create them from a run, two runs, or a dataset version. */
export function QueueList() {
  const { organization, project } = useWorkspace();
  const queues = useLoader(() => api<LabelQueue[]>(`/projects/${project!.id}/label-queues`), [project?.id]);
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;

  return (
    <div>
      <PageHeader
        title="Labeling"
        description="Human verdicts on outputs: grade a run, pick the better of two runs, or verify a dataset's expected answers. Verdicts become labels the judges are calibrated against."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name, href: base }, { label: "Labeling" }]}
        actions={isAdmin(organization.role) ? <QueueForm projectId={project.id} base={base} /> : undefined}
      />
      {queues.error ? (
        <LoadError what="queues" error={queues.error} retry={queues.reload} />
      ) : queues.loading && !queues.data ? (
        <Skeleton className="h-40 w-full" data-testid="loading" />
      ) : !queues.data || queues.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">No queues yet. {isAdmin(organization.role) ? "Create one from a run or a dataset version." : "An admin creates them from a run or a dataset version."}</p>
      ) : (
        <Table aria-label="Queues">
          <TableHeader>
            <TableRow>
              <TableHead>Queue</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Tasks</TableHead>
              <TableHead>Label key</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {queues.data.map((q) => (
              <TableRow key={q.id}>
                <TableCell>
                  <Link href={`${base}/labeling/${q.id}`} className="font-medium underline-offset-4 hover:underline">
                    {q.name}
                  </Link>
                </TableCell>
                <TableCell>{KIND_LABEL[q.kind]}</TableCell>
                <TableCell>
                  <Badge variant={q.status === "open" ? "default" : "secondary"}>{q.status}</Badge>
                </TableCell>
                <TableCell>{q.task_count}</TableCell>
                <TableCell className="font-mono text-xs">{q.kind === "compare" ? "compare:<run b>" : q.check_key || "overall"}</TableCell>
                <TableCell>{when(q.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
