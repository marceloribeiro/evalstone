"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { pct, signed, usd, when } from "@/lib/format";
import type { Comparison, Flip, Page, Run } from "@/lib/types";

/**
 * This run relative to another run of the same suite (the library's `compare()`): the suite
 * baseline by default, any earlier run otherwise. Regressions = passed before, fails now.
 */
export function CompareView({ projectId, run, base }: { projectId: string; run: Run; base: string }) {
  const candidates = useLoader(
    () => api<Page<Run>>(`/projects/${projectId}/runs`, { query: { suite: run.suite, limit: 100 } }).then((p) => p.items.filter((r) => r.id !== run.id)),
    [projectId, run.suite, run.id],
  );
  const [picked, setPicked] = useState<string | null>(null);
  const others = candidates.data ?? [];
  const baseline = others.find((r) => r.is_baseline);
  const against = picked ? others.find((r) => r.id === picked) : baseline ?? others[0];
  const cmp = useLoader(
    () => (against ? api<Comparison>(`/projects/${projectId}/runs/${against.id}/compare/${run.id}`) : Promise.resolve(null)),
    [projectId, run.id, against?.id],
  );

  if (candidates.loading && !candidates.data) return <Skeleton className="mt-4 h-24 w-full" />;
  if (others.length === 0) return <p className="mt-4 text-sm text-muted-foreground">No other run of suite &quot;{run.suite}&quot; to compare with yet.</p>;
  const items: Record<string, string> = Object.fromEntries(others.map((r) => [r.id, `${r.client_run_id}${r.is_baseline ? " (baseline)" : ""} · ${pct(r.pass_rate)} · ${when(r.finished_at)}`]));

  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm">Against</span>
        <Select value={against?.id ?? null} onValueChange={(v) => setPicked(v)} items={items}>
          <SelectTrigger aria-label="Compare against" className="w-[28rem] max-w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {others.map((r) => (
              <SelectItem key={r.id} value={r.id}>
                {items[r.id]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {against && (
          <Link href={`${base}/runs/${against.id}`} className="text-sm underline-offset-4 hover:underline">
            open
          </Link>
        )}
      </div>
      {cmp.loading && !cmp.data ? (
        <Skeleton className="h-24 w-full" />
      ) : cmp.data ? (
        <div data-testid="comparison">
          {!cmp.data.same_dataset && (
            <p className="mb-3 text-sm text-destructive">Different datasets — only the samples both runs share are compared.</p>
          )}
          <dl className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5" aria-label="Deltas">
            <Delta label="Pass rate" value={signed(cmp.data.pass_rate_delta, (v) => pct(v))} good={cmp.data.pass_rate_delta >= 0} />
            <Delta label="Mean score" value={signed(cmp.data.mean_score_delta, (v) => v.toFixed(3))} good={cmp.data.mean_score_delta >= 0} />
            <Delta label="Cost" value={signed(cmp.data.cost_delta, usd)} good={cmp.data.cost_delta <= 0} />
            <Delta label="Regressions" value={String(cmp.data.regressions.length)} good={cmp.data.regressions.length === 0} />
            <Delta label="Improvements" value={String(cmp.data.improvements.length)} good />
          </dl>
          <Flips title="Regressions" flips={cmp.data.regressions} tone="destructive" />
          <Flips title="Improvements" flips={cmp.data.improvements} tone="default" />
          {(cmp.data.only_in_a.length > 0 || cmp.data.only_in_b.length > 0) && (
            <p className="mt-3 text-sm text-muted-foreground">
              {cmp.data.only_in_a.length} result{cmp.data.only_in_a.length === 1 ? "" : "s"} only in the other run · {cmp.data.only_in_b.length} only in this one.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}

function Delta({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={`text-lg font-semibold ${good ? "" : "text-destructive"}`}>{value}</dd>
    </div>
  );
}

function Flips({ title, flips, tone }: { title: string; flips: Flip[]; tone: "destructive" | "default" }) {
  if (flips.length === 0) return null;
  return (
    <div className="mb-4">
      <p className="mb-1 text-sm font-medium">
        {title} <Badge variant={tone}>{flips.length}</Badge>
      </p>
      <Table aria-label={title}>
        <TableHeader>
          <TableRow>
            <TableHead>Sample</TableHead>
            <TableHead>Check</TableHead>
            <TableHead>Before</TableHead>
            <TableHead>After</TableHead>
            <TableHead>Reason now</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {flips.map((f) => (
            <TableRow key={`${f.sample_id}/${f.check_key}`}>
              <TableCell className="font-mono text-xs">{f.sample_id}</TableCell>
              <TableCell className="font-mono text-xs">{f.check_key}</TableCell>
              <TableCell>{f.before.value.toFixed(2)}</TableCell>
              <TableCell>{f.after.value.toFixed(2)}</TableCell>
              <TableCell className="max-w-md truncate text-muted-foreground">{f.after.error ?? f.after.reason}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
