"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLiveEvent } from "@/contexts/WebSocketContext";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { pct, usd, when } from "@/lib/format";
import type { Page, Run } from "@/lib/types";

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
  // the suite filter lists every suite the project has pushed, not only the current page's
  const suites = useLoader(
    () => api<Page<Run>>(`/projects/${project!.id}/runs`, { query: { limit: 500 } }).then((p) => [...new Set(p.items.map((r) => r.suite))].sort()),
    [project?.id],
  );
  useLiveEvent("run.stored", () => {
    runs.reload();
    suites.reload();
  });
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const total = runs.data?.total ?? 0;
  const items: Record<string, string> = { [ALL]: "All suites", ...Object.fromEntries((suites.data ?? []).map((s) => [s, s])) };

  return (
    <div>
      <PageHeader
        title="Runs"
        description="Every report pushed to this project, newest first."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name, href: base }, { label: "Runs" }]}
        actions={
          <Select
            value={suite}
            onValueChange={(v) => {
              setSuite(v ?? ALL);
              setOffset(0);
            }}
            items={items}
          >
            <SelectTrigger aria-label="Suite" className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(items).map(([v, label]) => (
                <SelectItem key={v} value={v}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />
      {runs.loading && !runs.data ? (
        <Skeleton className="h-40 w-full" data-testid="loading" />
      ) : !runs.data || runs.data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No runs stored yet. Push one with <code>evalstone run</code> against this project.</p>
      ) : (
        <>
          <Table aria-label="Runs">
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
          <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={offset + LIMIT >= total} onClick={() => setOffset(offset + LIMIT)}>
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
