"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PickOne } from "@/components/common/PickOne";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { pct } from "@/lib/format";
import type { Dataset, DatasetVersion, LabelQueue, Page, QueueKind, Run } from "@/lib/types";

const KINDS: Record<QueueKind, string> = { grade: "Grade outputs of a run", compare: "A/B compare two runs", verify: "Verify a dataset version" };

/** "New queue": pick a kind, then its source (run / two runs / dataset version), instructions, label key, scale. */
export function QueueForm({ projectId, base }: { projectId: string; base: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<QueueKind>("grade");
  const [runId, setRunId] = useState<string | null>(null);
  const [runB, setRunB] = useState<string | null>(null);
  const [checkKey, setCheckKey] = useState<string>("");
  const [failedOnly, setFailedOnly] = useState(false);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [labelKey, setLabelKey] = useState("");
  const [scale, setScale] = useState("5");
  const [instructions, setInstructions] = useState("");
  const [busy, setBusy] = useState(false);

  const runs = useLoader(() => (open ? api<Page<Run>>(`/projects/${projectId}/runs`, { query: { limit: 100 } }).then((p) => p.items) : Promise.resolve([] as Run[])), [projectId, open]);
  const datasets = useLoader(() => (open ? api<Dataset[]>(`/projects/${projectId}/datasets`) : Promise.resolve([] as Dataset[])), [projectId, open]);
  const versions = useLoader(
    () => (datasetId ? api<DatasetVersion[]>(`/projects/${projectId}/datasets/${datasetId}/versions`) : Promise.resolve([] as DatasetVersion[])),
    [projectId, datasetId],
  );
  const runItems: Record<string, string> = Object.fromEntries((runs.data ?? []).map((r) => [r.id, `${r.client_run_id} · ${r.suite} · ${pct(r.pass_rate)}`]));
  const run = runs.data?.find((r) => r.id === runId);
  const checkItems: Record<string, string> = { "": "every check", ...Object.fromEntries((run?.check_keys ?? []).map((k) => [k, k])) };
  const datasetItems: Record<string, string> = Object.fromEntries((datasets.data ?? []).map((d) => [d.id, d.name]));
  const versionItems: Record<string, string> = Object.fromEntries((versions.data ?? []).map((v) => [String(v.version), `v${v.version} · ${v.sample_count} samples`]));

  const source =
    kind === "grade"
      ? runId && { run_id: runId, ...(checkKey ? { check_key: checkKey } : {}), ...(failedOnly ? { failed_only: true } : {}) }
      : kind === "compare"
        ? runId && runB && runId !== runB && { run_a: runId, run_b: runB }
        : datasetId && version && { dataset_id: datasetId, version: Number(version) };

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!source) return;
    setBusy(true);
    try {
      const q = await api<LabelQueue>(`/projects/${projectId}/label-queues`, {
        method: "POST",
        body: { name: name.trim(), kind, source, instructions, check_key: kind === "compare" ? "" : labelKey.trim(), scale: Number(scale) },
      });
      toast.success(`Queue "${q.name}" created with ${q.task_count} task${q.task_count === 1 ? "" : "s"}`);
      setOpen(false);
      router.push(`${base}/labeling/${q.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>New queue</Button>} />
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New labeling queue</DialogTitle>
          <DialogDescription>One task per sample; labelers claim them one at a time.</DialogDescription>
        </DialogHeader>
        <form onSubmit={create} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="queue-name">Name</Label>
            <Input id="queue-name" required value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="space-y-1">
            <Label>Kind</Label>
            <PickOne label="Kind" value={kind} items={KINDS} onChange={(v) => setKind((v as QueueKind) ?? "grade")} className="w-full" />
          </div>
          {kind !== "verify" && (
            <div className="space-y-1">
              <Label>{kind === "compare" ? "Run A" : "Run"}</Label>
              <PickOne label={kind === "compare" ? "Run A" : "Run"} value={runId} items={runItems} onChange={setRunId} className="w-full" />
            </div>
          )}
          {kind === "compare" && (
            <div className="space-y-1">
              <Label>Run B</Label>
              <PickOne label="Run B" value={runB} items={runItems} onChange={setRunB} className="w-full" />
            </div>
          )}
          {kind === "grade" && (
            <>
              <div className="space-y-1">
                <Label>Source check</Label>
                <PickOne label="Source check" value={checkKey} items={checkItems} onChange={(v) => setCheckKey(v ?? "")} className="w-full" />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} />
                Failed results only
              </label>
            </>
          )}
          {kind === "verify" && (
            <>
              <div className="space-y-1">
                <Label>Dataset</Label>
                <PickOne label="Dataset" value={datasetId} items={datasetItems} onChange={(v) => { setDatasetId(v); setVersion(null); }} className="w-full" />
              </div>
              <div className="space-y-1">
                <Label>Version</Label>
                <PickOne label="Version" value={version} items={versionItems} onChange={setVersion} className="w-full" />
              </div>
            </>
          )}
          {kind !== "compare" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="queue-label-key">Label key</Label>
                <Input id="queue-label-key" value={labelKey} onChange={(e) => setLabelKey(e.target.value)} placeholder="overall" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="queue-scale">Scale (2 = pass/fail)</Label>
                <Input id="queue-scale" type="number" min={2} max={10} value={scale} onChange={(e) => setScale(e.target.value)} />
              </div>
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="queue-instructions">Instructions for labelers</Label>
            <Textarea id="queue-instructions" rows={3} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
          </div>
          <Button type="submit" disabled={busy || !name.trim() || !source}>
            Create
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
