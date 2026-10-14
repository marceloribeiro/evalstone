"use client";

import { Fragment, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Pager } from "@/components/common/Pager";
import { LoadError } from "@/components/common/LoadError";
import { useLoader } from "@/hooks/useLoader";
import { api } from "@/lib/api";
import { brief } from "@/lib/format";
import type { DatasetVersion, Page, Sample } from "@/lib/types";

const LIMIT = 50;

/** The samples of one version in position order; click a row for the full input / expected / metadata. */
export function SampleBrowser({ projectId, datasetId, version }: { projectId: string; datasetId: string; version: DatasetVersion }) {
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const samples = useLoader(
    () => api<Page<Sample>>(`/projects/${projectId}/datasets/${datasetId}/versions/${version.version}/samples`, { query: { offset, limit: LIMIT } }),
    [projectId, datasetId, version.version, offset],
  );
  if (samples.error) return <LoadError what="the samples" error={samples.error} retry={samples.reload} />;
  if (samples.loading && !samples.data) return <Skeleton className="mt-4 h-40 w-full" />;
  const total = samples.data?.total ?? 0;
  return (
    <div className="mt-4">
      <Table aria-label="Samples" className={samples.loading ? "opacity-60" : undefined} aria-busy={samples.loading}>
        <TableHeader>
          <TableRow>
            <TableHead>Sample</TableHead>
            <TableHead>Input</TableHead>
            <TableHead>Expected</TableHead>
            <TableHead>Tags</TableHead>
            <TableHead>Source</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {samples.data?.items.map((s) => (
            <Fragment key={s.id}>
              <TableRow className="cursor-pointer" onClick={() => setOpen(open === s.id ? null : s.id)} aria-expanded={open === s.id}>
                <TableCell className="font-mono text-xs">{s.sample_key}</TableCell>
                <TableCell className="max-w-md truncate">{brief(s.input, 120)}</TableCell>
                <TableCell className="max-w-sm truncate text-muted-foreground">{brief(s.expected, 80)}</TableCell>
                <TableCell>
                  <ul className="flex flex-wrap gap-1">
                    {s.tags.map((t) => (
                      <li key={t}>
                        <Badge variant="outline">{t}</Badge>
                      </li>
                    ))}
                  </ul>
                </TableCell>
                <TableCell className="text-muted-foreground">{s.source}</TableCell>
              </TableRow>
              {open === s.id && (
                <TableRow>
                  <TableCell colSpan={5} className="bg-muted/40">
                    <dl className="grid gap-2 text-xs md:grid-cols-3" data-testid="sample-detail">
                      <Field label="Input" value={s.input} />
                      <Field label="Expected" value={s.expected} />
                      <Field label="Metadata" value={s.metadata} />
                      <Field label="Content hash" value={s.content_hash} />
                    </dl>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          ))}
          {samples.data && samples.data.items.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="text-muted-foreground">
                This version is empty.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
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
