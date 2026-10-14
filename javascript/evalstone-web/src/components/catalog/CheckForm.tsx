"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PickOne } from "@/components/common/PickOne";
import { ParamFields } from "@/components/catalog/ParamFields";
import { useAction } from "@/hooks/useAction";
import { api } from "@/lib/api";
import { buildParams, toField, widgetFor } from "@/lib/checkParams";
import type { BuiltinCheck, CatalogCheck } from "@/lib/types";

/** Create a check (type + key + params) or edit an existing one's type/params (a content change needs a note → new version). */
export function CheckForm({ organizationId, builtins, existing, onSaved, trigger }: { organizationId: string; builtins: BuiltinCheck[]; existing?: CatalogCheck; onSaved: (check: CatalogCheck) => void; trigger: React.ReactElement }) {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<string | null>(existing?.type ?? null);
  const [key, setKey] = useState(existing?.key ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [note, setNote] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const { busy, act } = useAction();
  const builtin = builtins.find((b) => b.type === type);
  const typeItems: Record<string, string> = useMemo(
    () => Object.fromEntries(builtins.filter((b) => b.storable).map((b) => [b.type, `${b.type} — ${b.kind}`])),
    [builtins],
  );
  const { params, errors } = builtin ? buildParams(builtin.params, fields) : { params: {}, errors: {} };
  const keyOk = /^[a-z0-9._-]{1,200}$/.test(key.trim());
  const valid = !!builtin && keyOk && Object.keys(errors).length === 0;

  const pick = (t: string | null) => {
    setType(t);
    const b = builtins.find((x) => x.type === t);
    // prefill from the stored params when editing the same type, else from the factory defaults
    const source = existing && existing.type === t ? existing.params : {};
    setFields(Object.fromEntries((b?.params ?? []).map((p) => [p.name, toField(widgetFor(p), source[p.name] ?? p.default)])));
  };
  const onOpen = (o: boolean) => {
    setOpen(o);
    if (o) pick(existing?.type ?? null);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid || !builtin) return;
    const saved = existing
      ? await act(`Check "${existing.key}" saved`, () => api<CatalogCheck>(`/organizations/${organizationId}/checks/${existing.id}`, { method: "PUT", body: { type: builtin.type, params, description, note: note.trim() } }))
      : await act(`Check "${key.trim()}" created`, () => api<CatalogCheck>(`/organizations/${organizationId}/checks`, { method: "POST", body: { key: key.trim(), type: builtin.type, params, description } }));
    if (saved) {
      setOpen(false);
      setNote("");
      onSaved(saved);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpen}>
      <DialogTrigger render={trigger} />
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{existing ? `Edit "${existing.key}"` : "New check"}</DialogTitle>
          <DialogDescription>{existing ? "Changing the type or params creates the next version; add a note saying why." : "A check type from the library this center runs, with the params its factory takes. Monitors and the library's `checks: yaml` pull use it by key."}</DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="space-y-4" aria-label={existing ? "Edit check form" : "New check form"}>
          {!existing && (
            <div className="space-y-1">
              <Label htmlFor="check-key">Key</Label>
              <Input id="check-key" required value={key} onChange={(e) => setKey(e.target.value)} className="font-mono" placeholder="has-paris" autoFocus />
              {key && !keyOk && (
                <p className="text-xs text-destructive" role="alert">
                  lowercase letters, digits, &quot;.&quot;, &quot;_&quot; or &quot;-&quot; only
                </p>
              )}
            </div>
          )}
          <div className="space-y-1">
            <Label>Type</Label>
            <PickOne label="Check type" value={type} items={typeItems} onChange={pick} className="w-full" />
            {builtin && <p className="text-xs text-muted-foreground">{builtin.summary}</p>}
          </div>
          {builtin && <ParamFields params={builtin.params} fields={fields} errors={errors} onChange={(n, v) => setFields({ ...fields, [n]: v })} idPrefix="param" />}
          <div className="space-y-1">
            <Label htmlFor="check-description">Description</Label>
            <Textarea id="check-description" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          {existing && (
            <div className="space-y-1">
              <Label htmlFor="check-note">Version note (for a type/params change)</Label>
              <Input id="check-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="why this changed" />
            </div>
          )}
          <Button type="submit" disabled={busy || !valid}>
            {existing ? "Save" : "Create"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
