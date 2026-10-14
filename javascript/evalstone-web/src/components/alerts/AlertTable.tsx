"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { when } from "@/lib/format";
import { METRIC_LABEL, metricValue } from "@/lib/monitoring";
import type { Alert, AlertPolicy } from "@/lib/types";

/** Alerts, open first; `monitors` maps monitor id → name (and `base` makes the name a link). */
export function AlertTable({ alerts, monitors, loading, base }: { alerts: Alert[]; monitors: Record<string, string>; loading?: boolean; base?: string }) {
  if (loading) return <Skeleton className="h-24 w-full" />;
  if (alerts.length === 0) return <p className="text-sm text-muted-foreground">No alerts.</p>;
  const sorted = [...alerts].sort((a, b) => Number(!!a.resolved_at) - Number(!!b.resolved_at) || b.opened_at.localeCompare(a.opened_at));
  return (
    <Table aria-label="Alerts">
      <TableHeader>
        <TableRow>
          <TableHead>State</TableHead>
          <TableHead>Monitor</TableHead>
          <TableHead>Metric</TableHead>
          <TableHead>Value</TableHead>
          <TableHead>Threshold</TableHead>
          <TableHead>n</TableHead>
          <TableHead>Opened</TableHead>
          <TableHead>Resolved</TableHead>
          <TableHead>Webhook</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((a) => (
          <TableRow key={a.id} data-testid={`alert-${a.id}`} data-state={a.resolved_at ? "resolved" : "open"}>
            <TableCell>
              <Badge variant={a.resolved_at ? "secondary" : "destructive"}>{a.resolved_at ? "resolved" : "open"}</Badge>
            </TableCell>
            <TableCell>
              {base ? (
                <Link href={`${base}/monitors/${a.monitor_id}`} className="underline-offset-4 hover:underline">
                  {monitors[a.monitor_id] ?? a.monitor_id.slice(0, 8)}
                </Link>
              ) : (
                (monitors[a.monitor_id] ?? a.monitor_id.slice(0, 8))
              )}
            </TableCell>
            <TableCell>{METRIC_LABEL[a.metric as AlertPolicy["metric"]] ?? a.metric}</TableCell>
            <TableCell className={a.resolved_at ? "" : "text-destructive"}>{metricValue(a.metric, a.value)}</TableCell>
            <TableCell>{metricValue(a.metric, a.threshold)}</TableCell>
            <TableCell>
              {a.n} / {a.window_minutes} min
            </TableCell>
            <TableCell className="text-xs">{when(a.opened_at)}</TableCell>
            <TableCell className="text-xs">{a.resolved_at ? when(a.resolved_at) : "—"}</TableCell>
            <TableCell className="text-xs">
              {a.notify_error ? <span className="text-destructive" title={a.notify_error}>failed</span> : a.notified_at ? "sent" : <span className="text-muted-foreground">—</span>}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
