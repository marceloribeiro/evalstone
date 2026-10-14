"use client";

import { Fragment, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError } from "@/components/common/LoadError";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLiveEvent } from "@/contexts/WebSocketContext";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { pct, when } from "@/lib/format";
import { isAdmin } from "@/lib/roles";
import type { Calibration, JudgeSeen, JudgeSettings } from "@/lib/types";

type Loaded<T> = ReturnType<typeof useLoader<T>>;

/**
 * The judge versions seen in this project's results, the calibrations run against human labels
 * (agreement, Cohen's kappa, mean absolute error, confusion), and Promote: make a calibrated
 * judge's model the override for its check.
 */
export function CalibrationsCard({ projectId, settings }: { projectId: string; settings: Loaded<JudgeSettings> }) {
  const { organization } = useWorkspace();
  const admin = isAdmin(organization?.role);
  const judges = useLoader(() => api<JudgeSeen[]>(`/projects/${projectId}/judges`), [projectId]);
  const calibrations = useLoader(() => api<Calibration[]>(`/projects/${projectId}/calibrations`), [projectId]);
  useLiveEvent("calibration.finished", () => calibrations.reload());
  const [request, setRequest] = useState<JudgeSeen | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const promote = async (c: Calibration) => {
    if (!settings.data || !c.model) return;
    setBusy(true);
    try {
      await api(`/projects/${projectId}/judge-settings`, {
        method: "PUT",
        body: { default_model: settings.data.default_model, overrides: { ...settings.data.overrides, [c.check_key]: c.model } },
      });
      toast.success(`${c.check_key} now runs on ${c.model}`);
      settings.reload();
    } catch (err) {
      toast.error(errorMessage(err)); // e.g. the model's provider is not one of the organization's
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Judges seen</CardTitle>
          <CardDescription>Every (check, judge version) in stored results. A version is the hash of the check&apos;s prompt, scale and model — it changes when any of them does.</CardDescription>
        </CardHeader>
        <CardContent>
          {judges.error ? (
            <LoadError what="the judges" error={judges.error} retry={judges.reload} />
          ) : judges.loading && !judges.data ? (
            <Skeleton className="h-20 w-full" />
          ) : !judges.data?.length ? (
            <p className="text-sm text-muted-foreground">No judge verdicts stored yet. Runs with an LLM judge check will show up here.</p>
          ) : (
            <Table aria-label="Judges seen">
              <TableHeader>
                <TableRow>
                  <TableHead>Check</TableHead>
                  <TableHead>Judge version</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Results</TableHead>
                  <TableHead>Runs</TableHead>
                  <TableHead>Last seen</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {judges.data.map((j) => (
                  <TableRow key={`${j.check_key}/${j.judge_version}`}>
                    <TableCell className="font-mono text-xs">{j.check_key}</TableCell>
                    <TableCell className="font-mono text-xs">{j.judge_version}</TableCell>
                    <TableCell className="font-mono text-xs">{j.model ?? "—"}</TableCell>
                    <TableCell>{j.results}</TableCell>
                    <TableCell>{j.runs}</TableCell>
                    <TableCell>{when(j.last_seen)}</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="outline" onClick={() => setRequest(j)}>
                        Calibrate
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Calibrations</CardTitle>
          <CardDescription>Judge verdicts vs human labels on the same outputs. Agreement is the share of matching pass/fail; kappa corrects for chance (1 = perfect, 0 = chance).</CardDescription>
        </CardHeader>
        <CardContent>
          {calibrations.error ? (
            <LoadError what="the calibrations" error={calibrations.error} retry={calibrations.reload} />
          ) : calibrations.loading && !calibrations.data ? (
            <Skeleton className="h-20 w-full" />
          ) : !calibrations.data?.length ? (
            <p className="text-sm text-muted-foreground">None yet. Label some outputs (Labeling), then press Calibrate on a judge above.</p>
          ) : (
            <Table aria-label="Calibrations">
              <TableHeader>
                <TableRow>
                  <TableHead>Check</TableHead>
                  <TableHead>Judge version</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>n</TableHead>
                  <TableHead>Agreement</TableHead>
                  <TableHead>Kappa</TableHead>
                  <TableHead>MAE</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>When</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {calibrations.data.map((c) => (
                  <Fragment key={c.id}>
                    <TableRow className="cursor-pointer" data-testid={`calibration-${c.id}`} onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id}>
                      <TableCell className="font-mono text-xs">{c.check_key}</TableCell>
                      <TableCell className="font-mono text-xs">{c.judge_version}</TableCell>
                      <TableCell>
                        <Badge variant={c.status === "done" ? "default" : c.status === "failed" ? "destructive" : "secondary"}>{c.status}</Badge>
                      </TableCell>
                      <TableCell>{c.n}</TableCell>
                      <TableCell>{c.agreement == null ? "—" : pct(c.agreement)}</TableCell>
                      <TableCell>{c.kappa == null ? "—" : c.kappa.toFixed(2)}</TableCell>
                      <TableCell>{c.mean_abs_error == null ? "—" : c.mean_abs_error.toFixed(3)}</TableCell>
                      <TableCell className="font-mono text-xs">{c.model ?? "—"}</TableCell>
                      <TableCell>{when(c.finished_at ?? c.created_at)}</TableCell>
                      <TableCell className="text-right">
                        {admin && c.status === "done" && c.model && (
                          <Button
                            size="sm"
                            variant={settings.data?.overrides[c.check_key] === c.model ? "secondary" : "outline"}
                            disabled={busy || settings.data?.overrides[c.check_key] === c.model}
                            onClick={(e) => {
                              e.stopPropagation();
                              promote(c);
                            }}
                          >
                            {settings.data?.overrides[c.check_key] === c.model ? "Promoted" : "Promote"}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                    {open === c.id && (
                      <TableRow>
                        <TableCell colSpan={10} className="bg-muted/40">
                          {c.status === "failed" ? (
                            <p className="text-sm text-destructive" data-testid="calibration-error">
                              {c.error}
                            </p>
                          ) : (
                            <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4" aria-label="Confusion" data-testid="confusion">
                              <Cell label="Both pass" value={c.confusion.tp} />
                              <Cell label="Judge pass, human fail" value={c.confusion.fp} />
                              <Cell label="Judge fail, human pass" value={c.confusion.fn} />
                              <Cell label="Both fail" value={c.confusion.tn} />
                            </dl>
                          )}
                          <p className="mt-2 text-xs text-muted-foreground">
                            Labels under <code>{c.label_check || "overall"}</code>
                            {c.started_at && c.finished_at && <> · computed {when(c.finished_at)}</>}
                          </p>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <RequestDialog projectId={projectId} judge={request} onClose={() => setRequest(null)} onQueued={() => calibrations.reload()} />
    </>
  );
}

function Cell({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-lg font-semibold">{value ?? 0}</dd>
    </div>
  );
}

function RequestDialog({ projectId, judge, onClose, onQueued }: { projectId: string; judge: JudgeSeen | null; onClose: () => void; onQueued: () => void }) {
  const [labelCheck, setLabelCheck] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const value = labelCheck ?? judge?.check_key ?? "";
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!judge) return;
    setBusy(true);
    try {
      const c = await api<Calibration>(`/projects/${projectId}/calibrations`, {
        method: "POST",
        body: { check_key: judge.check_key, judge_version: judge.judge_version, label_check: value.trim() },
      });
      toast.success(c.status === "done" ? `Calibrated on ${c.n} outputs` : "Calibration queued");
      setLabelCheck(null);
      onQueued();
      onClose();
    } catch (err) {
      toast.error(errorMessage(err)); // e.g. no human labels under that check yet
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={!!judge} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Calibrate {judge?.check_key}</DialogTitle>
          <DialogDescription>
            Judge version <code>{judge?.judge_version}</code> against the human labels of this project.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="label-check">Labels under check (blank = the overall grade)</Label>
            <Input id="label-check" value={value} onChange={(e) => setLabelCheck(e.target.value)} className="font-mono" />
          </div>
          <Button type="submit" disabled={busy}>
            Run calibration
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
