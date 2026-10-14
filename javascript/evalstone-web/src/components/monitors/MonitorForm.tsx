"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PickOne } from "@/components/common/PickOne";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { METRIC_LABEL } from "@/lib/monitoring";
import type { AlertPolicy, CatalogCheck, Monitor } from "@/lib/types";

/** "New monitor": name, the catalog checks every sampled trace must pass, sample rate, the alert policy, an optional webhook. */
export function MonitorForm({ organizationId, projectId, base }: { organizationId: string; projectId: string; base: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [checks, setChecks] = useState<string[]>([]);
  const [sampleRate, setSampleRate] = useState("10");
  const [metric, setMetric] = useState<AlertPolicy["metric"]>("pass_rate");
  const [threshold, setThreshold] = useState("90");
  const [windowMinutes, setWindowMinutes] = useState("60");
  const [minN, setMinN] = useState("20");
  const [webhook, setWebhook] = useState("");
  const [busy, setBusy] = useState(false);
  const catalog = useLoader(() => (open ? api<CatalogCheck[]>(`/organizations/${organizationId}/checks`) : Promise.resolve([] as CatalogCheck[])), [organizationId, open]);

  const rate = Number(sampleRate) / 100;
  const thr = metric === "pass_rate" ? Number(threshold) / 100 : Number(threshold);
  const valid =
    name.trim() && checks.length > 0 && rate > 0 && rate <= 1 && thr >= 0 && thr <= 1 && Number.isInteger(Number(windowMinutes)) && Number(windowMinutes) >= 1 && Number.isInteger(Number(minN)) && Number(minN) >= 1;

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      const m = await api<Monitor>(`/projects/${projectId}/monitors`, {
        method: "POST",
        body: {
          name: name.trim(),
          check_keys: checks,
          sample_rate: rate,
          alert_policy: { metric, threshold: thr, window_minutes: Number(windowMinutes), min_n: Number(minN) },
          webhook_url: webhook.trim() || null,
        },
      });
      toast.success(`Monitor "${m.name}" created`);
      setOpen(false);
      router.push(`${base}/monitors/${m.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button>New monitor</Button>} />
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New monitor</DialogTitle>
          <DialogDescription>A sampled trace passes when every chosen check passes; the policy watches the window&apos;s metric.</DialogDescription>
        </DialogHeader>
        <form onSubmit={create} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="monitor-name">Name</Label>
            <Input id="monitor-name" required value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">Checks (from the organization&apos;s catalog)</legend>
            {catalog.data?.length ? (
              <ul className="grid gap-1 sm:grid-cols-2" aria-label="Catalog checks">
                {catalog.data.map((c) => (
                  <li key={c.id}>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={checks.includes(c.key)} onChange={(e) => setChecks(e.target.checked ? [...checks, c.key] : checks.filter((k) => k !== c.key))} />
                      <span className="font-mono text-xs">{c.key}</span> <span className="text-xs text-muted-foreground">({c.type})</span>
                    </label>
                  </li>
                ))}
              </ul>
            ) : catalog.loading ? (
              <p className="text-xs text-muted-foreground">Loading…</p>
            ) : (
              <p className="text-xs text-muted-foreground" data-testid="catalog-empty">
                The organization&apos;s check catalog is empty. Add a check first — the catalog editor is the next slice; until then <code>POST /organizations/{"{id}"}/checks</code> or the library&apos;s <code>checks/yaml</code> push.
              </p>
            )}
          </fieldset>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="monitor-sample">Sample rate (%)</Label>
              <Input id="monitor-sample" type="number" min={1} max={100} value={sampleRate} onChange={(e) => setSampleRate(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Metric</Label>
              <PickOne
                label="Metric"
                value={metric}
                items={METRIC_LABEL}
                onChange={(v) => {
                  const next = (v as AlertPolicy["metric"]) ?? "pass_rate";
                  if (next !== metric) {
                    // the threshold is a percentage for pass rate and a 0–1 value for mean score: convert, do not keep
                    const n = Number(threshold);
                    if (Number.isFinite(n)) setThreshold(next === "pass_rate" ? String(Math.round(n * 100 * 100) / 100) : String(Math.round(n) / 100));
                  }
                  setMetric(next);
                }}
                className="w-full"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="monitor-threshold">Alert below {metric === "pass_rate" ? "(%)" : "(0–1)"}</Label>
              <Input id="monitor-threshold" type="number" step="any" min={0} max={metric === "pass_rate" ? 100 : 1} value={threshold} onChange={(e) => setThreshold(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="monitor-window">Window (minutes)</Label>
              <Input id="monitor-window" type="number" min={1} max={10080} value={windowMinutes} onChange={(e) => setWindowMinutes(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="monitor-min-n">Minimum traces to alert</Label>
              <Input id="monitor-min-n" type="number" min={1} value={minN} onChange={(e) => setMinN(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="monitor-webhook">Webhook URL (optional)</Label>
              <Input id="monitor-webhook" value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder="https://hooks.example.com/…" />
            </div>
          </div>
          <Button type="submit" disabled={busy || !valid}>
            Create
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
