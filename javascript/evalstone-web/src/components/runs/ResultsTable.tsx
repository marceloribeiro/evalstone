"use client";

import { Fragment, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { brief, ms } from "@/lib/format";
import type { Page, Run, RunResult } from "@/lib/types";

const LIMIT = 50;
const ALL = "__all__";

/** Every (sample, check) result of a run: filter by check, failed only, expand a row for the full I/O. */
export function ResultsTable({ projectId, run }: { projectId: string; run: Run }) {
  const [check, setCheck] = useState<string>(ALL);
  const [failedOnly, setFailedOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const results = useLoader(
    () =>
      api<Page<RunResult>>(`/projects/${projectId}/runs/${run.id}/results`, {
        query: { limit: LIMIT, offset, check_key: check === ALL ? undefined : check, failed_only: failedOnly || undefined },
      }),
    [projectId, run.id, check, failedOnly, offset],
  );
  const items: Record<string, string> = { [ALL]: "All checks", ...Object.fromEntries(run.check_keys.map((k) => [k, k])) };
  const total = results.data?.total ?? 0;

  return (
    <div className="mt-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          value={check}
          onValueChange={(v) => {
            setCheck(v ?? ALL);
            setOffset(0);
          }}
          items={items}
        >
          <SelectTrigger aria-label="Check" className="w-56">
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
        <Button
          variant={failedOnly ? "default" : "outline"}
          size="sm"
          aria-pressed={failedOnly}
          onClick={() => {
            setFailedOnly(!failedOnly);
            setOffset(0);
          }}
        >
          Failed only
        </Button>
        <span className="ml-auto text-sm text-muted-foreground" data-testid="results-count">
          {total} result{total === 1 ? "" : "s"}
        </span>
      </div>
      {results.loading && !results.data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <Table aria-label="Results">
          <TableHeader>
            <TableRow>
              <TableHead>Sample</TableHead>
              <TableHead>Check</TableHead>
              <TableHead>Verdict</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Latency</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {results.data?.items.map((x) => (
              <Fragment key={x.id}>
                <TableRow className="cursor-pointer" onClick={() => setOpen(open === x.id ? null : x.id)} aria-expanded={open === x.id}>
                  <TableCell className="font-mono text-xs">{x.sample_key}</TableCell>
                  <TableCell className="font-mono text-xs">{x.check_key}</TableCell>
                  <TableCell>
                    {x.error ? <Badge variant="destructive">error</Badge> : x.skipped ? <Badge variant="outline">skipped</Badge> : x.passed ? <Badge>pass</Badge> : <Badge variant="destructive">fail</Badge>}
                  </TableCell>
                  <TableCell>{x.score.toFixed(2)}</TableCell>
                  <TableCell className="max-w-md truncate text-muted-foreground">{x.error ?? x.reason}</TableCell>
                  <TableCell>{ms(x.latency_ms)}</TableCell>
                </TableRow>
                {open === x.id && (
                  <TableRow>
                    <TableCell colSpan={6} className="bg-muted/40">
                      <dl className="grid gap-2 text-xs md:grid-cols-3" data-testid="result-detail">
                        <Field label="Input" value={x.input} />
                        <Field label="Expected" value={x.expected} />
                        <Field label="Output" value={x.output.value} />
                        {x.tags.length > 0 && <Field label="Tags" value={x.tags.join(", ")} />}
                        {x.output.model && <Field label="Model" value={x.output.model} />}
                        {(x.reason || x.error) && <Field label={x.error ? "Error" : "Reason"} value={x.error ?? x.reason} />}
                      </dl>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
            {results.data && results.data.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground">
                  Nothing matches.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
      {total > LIMIT && (
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
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <dt className="font-medium text-muted-foreground">{label}</dt>
      <dd className="whitespace-pre-wrap break-words font-mono">{brief(value, 2000)}</dd>
    </div>
  );
}
