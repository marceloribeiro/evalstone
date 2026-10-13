"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/layout/PageHeader";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLive } from "@/contexts/WebSocketContext";
import { api, errorMessage } from "@/lib/api";
import type { IngestKey, IngestKeyCreated, Page, Run } from "@/lib/types";
import { useLoader } from "@/hooks/useLoader";
import { useLiveEvent } from "@/contexts/WebSocketContext";
import { pct, when } from "@/lib/format";

/** The project home: how to attach, the live feed, the latest runs — the hero of the scaffold. */
export function ProjectOverview() {
  const { organization, project } = useWorkspace();
  const { status, recent } = useLive();
  const runs = useLoader(() => api<Page<Run>>(`/projects/${project!.id}/runs`, { query: { limit: 5 } }), [project?.id]);
  useLiveEvent("run.stored", () => runs.reload());
  // ingest keys are admin-only on the API (403 for a member): do not even ask for them
  const canManageKeys = organization?.role === "admin" || organization?.role === "owner";
  const keys = useLoader(
    () => (canManageKeys ? api<IngestKey[]>(`/projects/${project!.id}/ingest-keys`) : Promise.resolve([] as IngestKey[])),
    [project?.id, canManageKeys],
  );
  const [keyName, setKeyName] = useState("laptop");
  const [minted, setMinted] = useState<IngestKeyCreated | null>(null);
  if (!organization || !project) return null;

  const mint = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const k = await api<IngestKeyCreated>(`/projects/${project.id}/ingest-keys`, { method: "POST", body: { name: keyName } });
      setMinted(k);
      keys.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  return (
    <div>
      <PageHeader
        title={project.name}
        description={project.description || `Project ${project.slug}`}
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: project.name }]}
        actions={
          <Badge variant={status === "open" ? "default" : "secondary"} data-testid="live-status">
            {status === "open" ? "Live" : status === "connecting" ? "Connecting…" : "Offline"}
          </Badge>
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Attach your project</CardTitle>
            <CardDescription>Put this in your evalstone.yaml; judges run through the center with the organization&apos;s keys.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs" data-testid="attach-snippet">
{`center:
  url: ${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8181"}
  project: ${project.id}`}
            </pre>
            {canManageKeys ? (
            <form onSubmit={mint} className="flex items-end gap-2">
              <div className="space-y-1">
                <Label htmlFor="key-name">Ingest key name</Label>
                <Input id="key-name" value={keyName} onChange={(e) => setKeyName(e.target.value)} className="w-56" />
              </div>
              <Button type="submit" variant="outline">
                Create ingest key
              </Button>
            </form>
            ) : (
              <p className="text-sm text-muted-foreground">Ask an organization admin for an ingest key.</p>
            )}
            {minted && (
              <div role="status" className="rounded-md border border-dashed p-3 text-sm">
                <p className="font-medium">Copy it now — it is shown once.</p>
                <code className="mt-1 block break-all text-xs" data-testid="minted-key">
                  EVALSTONE_API_KEY={minted.key}
                </code>
              </div>
            )}
            {keys.data && keys.data.length > 0 && (
              <ul className="text-sm text-muted-foreground" aria-label="Ingest keys">
                {keys.data.map((k) => (
                  <li key={k.id}>
                    {k.name} · {k.prefix}… {k.revoked_at ? "(revoked)" : k.last_used_at ? `· last used ${when(k.last_used_at)}` : "· never used"}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Live</CardTitle>
            <CardDescription>Events from the center as they happen.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm" aria-label="Live events" data-testid="live-feed">
              {recent.length === 0 && <li className="text-muted-foreground">Nothing yet. Push a run to see it land here.</li>}
              {recent.map((e, i) => (
                <li key={`${e.at}-${i}`} className="flex items-start gap-2">
                  <Badge variant="outline">{e.event}</Badge>
                  <span className="text-muted-foreground">{summarize(e)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>
              <Link href={`/o/${organization.id}/p/${project.id}/runs`} className="underline-offset-4 hover:underline">
                Latest runs
              </Link>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {runs.data && runs.data.items.length ? (
              <table className="w-full text-sm" aria-label="Latest runs">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-1">Suite</th>
                    <th>Run</th>
                    <th>Pass rate</th>
                    <th>Results</th>
                    <th>Finished</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data.items.map((r) => (
                    <tr key={r.id} className="border-t">
                      <td className="py-1">{r.suite}</td>
                      <td className="font-mono text-xs">
                        <Link href={`/o/${organization.id}/p/${project.id}/runs/${r.id}`} className="underline-offset-4 hover:underline">
                          {r.client_run_id}
                        </Link>
                      </td>
                      <td>{pct(r.pass_rate)}</td>
                      <td>{r.result_count}</td>
                      <td>{when(r.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-muted-foreground">No runs stored yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function summarize(e: Record<string, unknown>): string {
  switch (e.event) {
    case "run.stored":
      return `${e.suite} · ${Math.round(Number(e.pass_rate) * 100)}% · ${e.result_count} results`;
    case "alert.opened":
      return `${e.metric} ${Number(e.value).toFixed(2)} < ${e.threshold}`;
    case "alert.resolved":
      return "recovered";
    case "calibration.finished":
      return `${e.check_key} · ${e.status}${e.agreement != null ? ` · agreement ${Number(e.agreement).toFixed(2)}` : ""}`;
    case "monitor.scored":
      return `${e.scored} traces scored`;
    case "traces.stored":
    case "labels.stored":
      return `${e.count} stored`;
    default:
      return "";
  }
}
