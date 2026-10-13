"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { ms, pct, usd, when } from "@/lib/format";
import type { Run } from "@/lib/types";
import { ResultsTable } from "@/components/runs/ResultsTable";
import { CompareView } from "@/components/runs/CompareView";

/** One run: the summary the library computed, the gate, per-check rates, every result, and a diff. */
export function RunDetail({ runId }: { runId: string }) {
  const { organization, project } = useWorkspace();
  const run = useLoader(() => api<Run>(`/projects/${project!.id}/runs/${runId}`), [project?.id, runId]);
  const [busy, setBusy] = useState(false);
  if (!organization || !project) return null;
  const base = `/o/${organization.id}/p/${project.id}`;
  const crumbs = [
    { label: "Home", href: "/organizations" },
    { label: organization.name, href: `/o/${organization.id}` },
    { label: project.name, href: base },
    { label: "Runs", href: `${base}/runs` },
    { label: run.data?.client_run_id ?? "…" },
  ];
  if (!run.data) return run.loading ? <Skeleton className="h-40 w-full" data-testid="loading" /> : <PageHeader title="Run not found" crumbs={crumbs} />;
  const r = run.data;
  const s = r.summary;

  const toggleBaseline = async () => {
    setBusy(true);
    try {
      await api(`/projects/${project.id}/runs/${r.id}/baseline`, { method: "PUT", body: { is_baseline: !r.is_baseline } });
      toast.success(r.is_baseline ? "Baseline unset" : `Baseline for suite "${r.suite}"`);
      run.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={r.client_run_id}
        description={
          <>
            Suite <strong>{r.suite}</strong> · dataset {r.dataset_name} <code className="text-xs">{r.dataset_hash.slice(0, 12)}</code> · {r.trigger}
            {r.git_sha && (
              <>
                {" "}
                · <code className="text-xs">{r.git_sha.slice(0, 10)}</code>
              </>
            )}{" "}
            · finished {when(r.finished_at)}
          </>
        }
        crumbs={crumbs}
        actions={
          <>
            {r.is_baseline && <Badge variant="secondary">Baseline</Badge>}
            <Button variant="outline" size="sm" disabled={busy} onClick={toggleBaseline}>
              {r.is_baseline ? "Unset baseline" : "Set as baseline"}
            </Button>
          </>
        }
      />

      <dl className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6" aria-label="Summary">
        <Stat label="Pass rate" value={pct(s.pass_rate)} />
        <Stat label="Mean score" value={s.mean_score.toFixed(3)} />
        <Stat label="Results" value={`${s.results} (${s.samples} × ${s.checks})`} />
        <Stat label="Errors" value={`${s.errors}${s.skipped ? ` · ${s.skipped} skipped` : ""}`} warn={s.errors > 0} />
        <Stat label="Cost" value={usd(s.cost_usd)} />
        <Stat label="Duration" value={ms(s.duration_ms)} />
      </dl>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Per check</CardTitle>
            <CardDescription>Where the run lost its points.</CardDescription>
          </CardHeader>
          <CardContent>
            <Table aria-label="Per check">
              <TableHeader>
                <TableRow>
                  <TableHead>Check</TableHead>
                  <TableHead>Pass rate</TableHead>
                  <TableHead>Passed</TableHead>
                  <TableHead>Mean score</TableHead>
                  <TableHead>Errors</TableHead>
                  <TableHead>Cost</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {s.per_check.map((c) => (
                  <TableRow key={c.key} data-testid={`check-${c.key}`}>
                    <TableCell className="font-mono text-xs">{c.key}</TableCell>
                    <TableCell className={c.pass_rate < 1 ? "text-destructive" : ""}>{pct(c.pass_rate)}</TableCell>
                    <TableCell>
                      {c.passed}/{c.n}
                    </TableCell>
                    <TableCell>{c.mean_score.toFixed(3)}</TableCell>
                    <TableCell>{c.errors}</TableCell>
                    <TableCell>{usd(c.cost_usd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>
              Gate{" "}
              {r.gate_passed == null ? (
                <Badge variant="outline">not evaluated</Badge>
              ) : (
                <Badge variant={r.gate_passed ? "default" : "destructive"}>{r.gate_passed ? "PASS" : "FAIL"}</Badge>
              )}
            </CardTitle>
            <CardDescription>The thresholds the CLI checked before exiting.</CardDescription>
          </CardHeader>
          <CardContent>
            {r.gate_lines.length ? (
              <ul className="space-y-1 font-mono text-xs" aria-label="Gate lines">
                {r.gate_lines.map((l, i) => (
                  <li key={i} className={l.startsWith("FAIL") ? "text-destructive" : ""}>
                    {l}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No gate on this run.</p>
            )}
            {Object.keys(s.per_tag).length > 0 && (
              <div className="mt-4">
                <p className="mb-1 text-sm font-medium">Per tag</p>
                <ul className="flex flex-wrap gap-2 text-xs" aria-label="Per tag">
                  {Object.entries(s.per_tag).map(([tag, rate]) => (
                    <li key={tag}>
                      <Badge variant="outline">
                        {tag} {pct(rate, 0)}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="results">
        <TabsList>
          <TabsTrigger value="results">Results</TabsTrigger>
          <TabsTrigger value="compare">Compare</TabsTrigger>
        </TabsList>
        <TabsContent value="results">
          <ResultsTable projectId={project.id} run={r} />
        </TabsContent>
        <TabsContent value="compare">
          <CompareView projectId={project.id} run={r} base={base} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={`text-lg font-semibold ${warn ? "text-destructive" : ""}`}>{value}</dd>
    </div>
  );
}
