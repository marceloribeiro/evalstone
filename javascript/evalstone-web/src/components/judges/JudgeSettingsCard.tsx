"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadError } from "@/components/common/LoadError";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { isAdmin } from "@/lib/roles";
import type { JudgeSettings, Provider } from "@/lib/types";

type Loaded<T> = ReturnType<typeof useLoader<T>>;

/**
 * `default_model` + per-check `overrides`, each a `<provider>/<model>` over the organization's
 * providers. Admins edit; the attached library and the center's own judges read this.
 */
export function JudgeSettingsCard({ organizationId, projectId, providers, settings }: { organizationId: string; projectId: string; providers: Loaded<Provider[]>; settings: Loaded<JudgeSettings> }) {
  const { organization } = useWorkspace();
  const admin = isAdmin(organization?.role);
  const [editing, setEditing] = useState(false);
  if (settings.error) return <LoadError what="the judge settings" error={settings.error} retry={settings.reload} />;
  if (!settings.data) return <Skeleton className="h-32 w-full" />;
  const s = settings.data;
  const names = (providers.data ?? []).map((p) => p.name);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Judge settings</CardTitle>
        <CardDescription>
          Models are <code>&lt;provider&gt;/&lt;model&gt;</code> over the organization&apos;s{" "}
          <Link href={`/o/${organizationId}/providers`} className="underline-offset-4 hover:underline">
            providers
          </Link>
          {names.length ? <> ({names.join(", ")})</> : <> — none yet</>}. A check without an override uses the default; without a default, the library&apos;s own `model:` applies.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {editing ? (
          <SettingsForm projectId={projectId} initial={s} onSaved={() => { setEditing(false); settings.reload(); }} onCancel={() => setEditing(false)} />
        ) : (
          <dl className="space-y-2 text-sm" data-testid="judge-settings">
            <div>
              <dt className="text-xs text-muted-foreground">Default model</dt>
              <dd className="font-mono">{s.default_model ?? <span className="font-sans text-muted-foreground">none</span>}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Overrides</dt>
              <dd>
                {Object.keys(s.overrides).length === 0 ? (
                  <span className="text-muted-foreground">none</span>
                ) : (
                  <ul className="font-mono" aria-label="Overrides">
                    {Object.entries(s.overrides).map(([check, model]) => (
                      <li key={check}>
                        {check} → {model}
                      </li>
                    ))}
                  </ul>
                )}
              </dd>
            </div>
            {admin && (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                Edit judge settings
              </Button>
            )}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function SettingsForm({ projectId, initial, onSaved, onCancel }: { projectId: string; initial: JudgeSettings; onSaved: () => void; onCancel: () => void }) {
  const [defaultModel, setDefaultModel] = useState(initial.default_model ?? "");
  const [overrides, setOverrides] = useState<{ check: string; model: string }[]>(Object.entries(initial.overrides).map(([check, model]) => ({ check, model })));
  const [busy, setBusy] = useState(false);
  const rows = overrides.filter((o) => o.check.trim() || o.model.trim());
  const complete = rows.every((o) => o.check.trim() && o.model.trim());

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!complete) return;
    setBusy(true);
    try {
      await api(`/projects/${projectId}/judge-settings`, {
        method: "PUT",
        body: { default_model: defaultModel.trim() || null, overrides: Object.fromEntries(rows.map((o) => [o.check.trim(), o.model.trim()])) },
      });
      toast.success("Judge settings saved");
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const update = (i: number, patch: Partial<{ check: string; model: string }>) => setOverrides(overrides.map((o, j) => (j === i ? { ...o, ...patch } : o)));

  return (
    <form onSubmit={save} className="space-y-4" aria-label="Judge settings form">
      <div className="space-y-1">
        <Label htmlFor="default-model">Default model</Label>
        <Input id="default-model" value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)} placeholder="openai/gpt-4o-mini" className="font-mono" />
      </div>
      <div className="space-y-2">
        <Label>Overrides (check → model)</Label>
        {overrides.map((o, i) => (
          <div key={i} className="flex gap-2">
            <Input aria-label={`Override ${i + 1} check`} value={o.check} onChange={(e) => update(i, { check: e.target.value })} placeholder="check key" className="font-mono" />
            <Input aria-label={`Override ${i + 1} model`} value={o.model} onChange={(e) => update(i, { model: e.target.value })} placeholder="provider/model" className="font-mono" />
            <Button type="button" variant="ghost" size="sm" aria-label={`Remove override ${i + 1}`} onClick={() => setOverrides(overrides.filter((_, j) => j !== i))}>
              ×
            </Button>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={() => setOverrides([...overrides, { check: "", model: "" }])}>
          Add override
        </Button>
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={busy || !complete}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
