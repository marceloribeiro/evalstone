"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError } from "@/components/common/LoadError";
import { Pager } from "@/components/common/Pager";
import { useLiveEvent } from "@/contexts/WebSocketContext";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { brief, ms, when } from "@/lib/format";
import type { Page, Trace } from "@/lib/types";

const LIMIT = 25;

/** The project's traces, newest first, with a flagged-only filter and per-row flagging; live on `traces.stored`. */
export function TraceTable({ projectId }: { projectId: string }) {
  const [offset, setOffset] = useState(0);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const traces = useLoader(
    () => api<Page<Trace>>(`/projects/${projectId}/traces`, { query: { offset, limit: LIMIT, flagged: flaggedOnly || undefined } }),
    [projectId, offset, flaggedOnly],
  );
  // apps push traces continuously: coalesce the live frames into one reload per 1.5 s (trailing)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reload = traces.reload;
  useLiveEvent("traces.stored", () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      reload();
    }, 1_500);
  });
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const flag = async (t: Trace) => {
    try {
      await api(`/projects/${projectId}/traces/${t.id}/flag`, { method: "POST", body: { flagged: !t.flagged } });
      traces.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  if (traces.error) return <LoadError what="the traces" error={traces.error} retry={traces.reload} />;
  const total = traces.data?.total ?? 0;
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Button
          size="sm"
          variant={flaggedOnly ? "default" : "outline"}
          aria-pressed={flaggedOnly}
          onClick={() => {
            setFlaggedOnly(!flaggedOnly);
            setOffset(0);
          }}
        >
          Flagged only
        </Button>
        <span className="ml-auto text-sm text-muted-foreground" data-testid="traces-count">
          {total} trace{total === 1 ? "" : "s"}
        </span>
      </div>
      {traces.loading && !traces.data ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <Table aria-label="Traces" className={traces.loading ? "opacity-60" : undefined} aria-busy={traces.loading}>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Input</TableHead>
              <TableHead>Output</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Latency</TableHead>
              <TableHead>Flag</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {traces.data?.items.map((t) => (
              <Fragment key={t.id}>
                <TableRow className="cursor-pointer" data-testid={`trace-${t.client_id}`} onClick={() => setOpen(open === t.id ? null : t.id)} aria-expanded={open === t.id}>
                  <TableCell className="whitespace-nowrap text-xs">{when(t.occurred_at)}</TableCell>
                  <TableCell className="max-w-xs truncate">{brief(t.input, 100)}</TableCell>
                  <TableCell className="max-w-sm truncate text-muted-foreground">{brief(t.output, 120)}</TableCell>
                  <TableCell className="font-mono text-xs">{t.model ?? "—"}</TableCell>
                  <TableCell>{t.latency_ms == null ? "—" : ms(t.latency_ms)}</TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant={t.flagged ? "default" : "ghost"}
                      aria-pressed={t.flagged}
                      aria-label={t.flagged ? `Unflag trace ${t.client_id}` : `Flag trace ${t.client_id}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        flag(t);
                      }}
                    >
                      {t.flagged ? "flagged" : "flag"}
                    </Button>
                  </TableCell>
                </TableRow>
                {open === t.id && (
                  <TableRow>
                    <TableCell colSpan={6} className="bg-muted/40">
                      <dl className="grid gap-2 text-xs md:grid-cols-3" data-testid="trace-detail">
                        <Field label="Input" value={t.input} />
                        <Field label="Output" value={t.output} />
                        <Field label="Metadata" value={t.metadata} />
                        <div>
                          <dt className="font-medium text-muted-foreground">Tags</dt>
                          <dd className="flex flex-wrap gap-1">
                            {t.tags.map((x) => (
                              <Badge key={x} variant="outline">
                                {x}
                              </Badge>
                            ))}
                          </dd>
                        </div>
                        <Field label="Client id" value={t.client_id} />
                        <Field label="Sample bucket" value={t.sample_bucket.toFixed(3)} />
                      </dl>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
            {traces.data && traces.data.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground">
                  {flaggedOnly ? "No flagged traces." : "No traces yet — push them with the ingest key (POST /projects/{id}/traces)."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
      <Pager offset={offset} limit={LIMIT} total={total} onChange={setOffset} />
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
