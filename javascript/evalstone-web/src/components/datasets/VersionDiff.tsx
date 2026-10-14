"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PickOne } from "@/components/common/PickOne";
import { LoadError } from "@/components/common/LoadError";
import { useLoader } from "@/hooks/useLoader";
import { diffSamples, fetchAllSamples } from "@/lib/datasetDiff";
import { brief } from "@/lib/format";
import type { DatasetVersion, Sample } from "@/lib/types";

/** Version `to` relative to an earlier version (the previous one by default): added, removed, changed samples. */
export function VersionDiff({ projectId, datasetId, versions, to }: { projectId: string; datasetId: string; versions: DatasetVersion[]; to: DatasetVersion }) {
  const others = versions.filter((v) => v.id !== to.id);
  const [picked, setPicked] = useState<number | null>(null);
  const previous = [...others].filter((v) => v.version < to.version).sort((a, b) => b.version - a.version)[0];
  const from = others.find((v) => v.version === picked) ?? previous ?? others[0];
  const diff = useLoader(
    () =>
      from
        ? Promise.all([fetchAllSamples(projectId, datasetId, from.version), fetchAllSamples(projectId, datasetId, to.version)]).then(([a, b]) => diffSamples(a, b))
        : Promise.resolve(null),
    [projectId, datasetId, from?.version, to.version],
  );
  if (others.length === 0) return <p className="mt-4 text-sm text-muted-foreground">Only one version so far — nothing to diff against.</p>;
  const items: Record<string, string> = Object.fromEntries(others.map((v) => [String(v.version), `v${v.version} · ${v.sample_count} samples`]));

  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span>
          v{to.version} relative to
        </span>
        <PickOne label="Diff against" value={from ? String(from.version) : null} items={items} onChange={(v) => setPicked(v ? Number(v) : null)} className="w-56" />
      </div>
      {diff.error ? (
        <LoadError what="the diff" error={diff.error} retry={diff.reload} />
      ) : diff.loading || !diff.data ? (
        <Skeleton className="h-24 w-full" data-testid="diff-loading" />
      ) : (
        <div data-testid="diff">
          <p className="mb-3 flex flex-wrap gap-2 text-sm">
            <Badge variant={diff.data.added.length ? "default" : "outline"}>{diff.data.added.length} added</Badge>
            <Badge variant={diff.data.removed.length ? "destructive" : "outline"}>{diff.data.removed.length} removed</Badge>
            <Badge variant={diff.data.changed.length ? "secondary" : "outline"}>{diff.data.changed.length} changed</Badge>
            <Badge variant="outline">{diff.data.unchanged} unchanged</Badge>
          </p>
          <Rows title="Added" rows={diff.data.added.map((s) => ({ key: s.sample_key, before: null, after: s }))} />
          <Rows title="Removed" rows={diff.data.removed.map((s) => ({ key: s.sample_key, before: s, after: null }))} />
          <Rows title="Changed" rows={diff.data.changed} />
        </div>
      )}
    </div>
  );
}

function Rows({ title, rows }: { title: string; rows: { key: string; before: Sample | null; after: Sample | null }[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="mb-4">
      <p className="mb-1 text-sm font-medium">{title}</p>
      <Table aria-label={title}>
        <TableHeader>
          <TableRow>
            <TableHead>Sample</TableHead>
            <TableHead>Before</TableHead>
            <TableHead>After</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.key}>
              <TableCell className="font-mono text-xs">{r.key}</TableCell>
              <TableCell className="max-w-md whitespace-pre-wrap break-words font-mono text-xs text-muted-foreground">{r.before ? summary(r.before) : "—"}</TableCell>
              <TableCell className="max-w-md whitespace-pre-wrap break-words font-mono text-xs">{r.after ? summary(r.after) : "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function summary(s: Sample): string {
  const parts = [`input: ${brief(s.input, 200)}`];
  if (s.expected != null) parts.push(`expected: ${brief(s.expected, 120)}`);
  if (s.tags.length) parts.push(`tags: ${s.tags.join(", ")}`);
  return parts.join("\n");
}
