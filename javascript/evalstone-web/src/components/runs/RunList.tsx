"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { Pager } from "@/components/common/Pager";
import { PickOne } from "@/components/common/PickOne";
import { LoadError } from "@/components/common/LoadError";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLiveEvent } from "@/contexts/WebSocketContext";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { pct, usd, when } from "@/lib/format";
import type { Page, Run, Suite } from "@/lib/types";

const LIMIT = 50;
const ALL = "__all__";

/** Run history for the project: newest first, filter by suite, page through, live on `run.stored`. */
export function RunList() {
  const { organization, project } = useWorkspace();
  const [suite, setSuite] = useState<string>(ALL);
  const [offset, setOffset] = useState(0);
  const runs = useLoader(
    () =>
      api<Page<Run>>(`/projects/${project!.id}/runs`, {
        query: { limit: LIMIT, offset, suite: suite === ALL ? undefined : suite },
      }),
    [project?.id, suite, offset],
  );
  // the distinct suites of the project (a grouped query on the API), not a scan of the newest runs
  const suites = useLoader(() => api<Suite[]>(`/projects/${project!.id}/runs/suites`), [project?.id]);
  useLiveEvent("run.stored", (e) => {
    runs.reload();
    if (!suites.data?.some((s) => s.suite === e.suite)) suites.reload(); // a new suite appeared
  });
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const total = runs.data?.total ?? 0;
  const items: Record<string, string> = { [ALL]: "All suites", ...Object.fromEntries((suites.data ?? []).map((s) => [s.suite, `${s.suite} (${s.runs})`])) };

  return (
    <div>
      <PageHeader
        title="Runs"
        description="Every report pushed to this project, newest first."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name, href: base }, { label: "Runs" }]}
        actions={
          <PickOne
            label="Suite"
            value={suite}
            items={items}
            className="w-48"
            onChange={(v) => {
              setSuite(v ?? ALL);
              setOffset(0);
            }}
          />
        }
      />
      {runs.error ? (
        <LoadError what="runs" error={runs.error} retry={runs.reload} />
      ) : runs.loading && !runs.data ? (
        <Skeleton className="h-40 w-full" data-testid="loading" />
      ) : !runs.data || runs.data.items.length === 0 ? (
        suite === ALL ? (
          <p className="text-sm text-muted-foreground">
            No runs stored yet. Push one with <code>evalstone run</code> against this project.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">No runs in suite &quot;{suite}&quot;.</p>
        )
      ) : (
        <>
          <Table aria-label="Runs" className={runs.loading ? "opacity-60" : undefined} aria-busy={runs.loading}>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>Suite</TableHead>
                <TableHead>Pass rate</TableHead>
                <TableHead>Mean score</TableHead>
                <TableHead>Results</TableHead>
                <TableHead>Gate</TableHead>
                <TableHead>Cost</TableHead>
                <TableHead>Trigger</TableHead>
                <TableHead>Finished</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data.items.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link href={`${base}/runs/${r.id}`} className="font-mono text-xs underline-offset-4 hover:underline">
                      {r.client_run_id}
                    </Link>
                    {r.is_baseline && (
                      <Badge variant="secondary" className="ml-2">
                        Baseline
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>{r.suite}</TableCell>
                  <TableCell>{pct(r.pass_rate)}</TableCell>
                  <TableCell>{r.mean_score.toFixed(3)}</TableCell>
                  <TableCell>
                    {r.result_count}
                    {r.summary.errors > 0 && <span className="ml-1 text-destructive">({r.summary.errors} errors)</span>}
                  </TableCell>
                  <TableCell>
                    {r.gate_passed == null ? <span className="text-muted-foreground">—</span> : <Badge variant={r.gate_passed ? "default" : "destructive"}>{r.gate_passed ? "PASS" : "FAIL"}</Badge>}
                  </TableCell>
                  <TableCell>{usd(r.cost_usd)}</TableCell>
                  <TableCell>{r.trigger}</TableCell>
                  <TableCell>{when(r.finished_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager offset={offset} limit={LIMIT} total={total} onChange={setOffset} />
        </>
      )}
    </div>
  );
}
