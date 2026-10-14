"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadError } from "@/components/common/LoadError";
import { PickOne } from "@/components/common/PickOne";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { useLoader } from "@/hooks/useLoader";
import { api, errorMessage } from "@/lib/api";
import { ms, when } from "@/lib/format";
import { isAdmin } from "@/lib/roles";
import type { Adapter, Provider, ProviderTest } from "@/lib/types";

const ADAPTERS: Record<Adapter, string> = { openai: "OpenAI-compatible (OpenAI, OpenRouter, Ollama, …)", anthropic: "Anthropic", gemini: "Google Gemini" };

/** The organization's model providers: keys are write-only (last 4 shown), each can be tested with a model id. */
export function ProviderList() {
  const { organization } = useWorkspace();
  const providers = useLoader(() => api<Provider[]>(`/organizations/${organization!.id}/providers`), [organization?.id]);
  if (!organization) return null;
  const admin = isAdmin(organization.role);

  return (
    <div>
      <PageHeader
        title="Providers"
        description="Where judges run. Keys are encrypted at rest and never shown again; judge settings on each project pick a <provider>/<model>."
        crumbs={[{ label: "Home", href: "/organizations" }, { label: organization.name, href: `/o/${organization.id}` }, { label: "Providers" }]}
        actions={admin ? <ProviderForm organizationId={organization.id} onCreated={providers.reload} /> : undefined}
      />
      {providers.error ? (
        <LoadError what="providers" error={providers.error} retry={providers.reload} />
      ) : providers.loading && !providers.data ? (
        <Skeleton className="h-40 w-full" data-testid="loading" />
      ) : !providers.data || providers.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">No providers yet. {admin ? "Add one with its API key, then test it with a model id." : "An admin adds them."}</p>
      ) : (
        <Table aria-label="Providers">
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Adapter</TableHead>
              <TableHead>Base URL</TableHead>
              <TableHead>Key</TableHead>
              <TableHead>Verified</TableHead>
              {admin && <TableHead />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {providers.data.map((p) => (
              <ProviderRow key={p.id} provider={p} organizationId={organization.id} admin={admin} onChanged={providers.reload} />
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function ProviderRow({ provider: p, organizationId, admin, onChanged }: { provider: Provider; organizationId: string; admin: boolean; onChanged: () => void }) {
  const [model, setModel] = useState("");
  const [result, setResult] = useState<ProviderTest | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const url = (path: string) => `/organizations/${organizationId}/providers/${p.id}${path}`;

  const test = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api<ProviderTest>(url("/test"), { method: "POST", body: { model: model.trim() } });
      setResult(r);
      onChanged(); // verified_ok / last_error are stamped on the row
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await api(url(""), { method: "DELETE" });
      toast.success(`Provider "${p.name}" deleted`);
      setConfirmDelete(false);
      onChanged();
    } catch (err) {
      toast.error(errorMessage(err)); // 409 while a project's judge settings route to it
    } finally {
      setBusy(false);
    }
  };

  return (
    <TableRow data-testid={`provider-${p.name}`}>
      <TableCell className="font-medium">{p.name}</TableCell>
      <TableCell>{p.adapter}</TableCell>
      <TableCell className="max-w-xs truncate font-mono text-xs text-muted-foreground">{p.base_url ?? "default"}</TableCell>
      <TableCell className="font-mono text-xs">{p.has_api_key ? (p.key_last4 ? `…${p.key_last4}` : "set") : <span className="text-muted-foreground">none</span>}</TableCell>
      <TableCell>
        {p.verified_ok == null ? (
          <span className="text-muted-foreground">never tested</span>
        ) : (
          <>
            <Badge variant={p.verified_ok ? "default" : "destructive"}>{p.verified_ok ? "ok" : "failed"}</Badge>
            {p.last_verified_at && <span className="ml-2 text-xs text-muted-foreground">{when(p.last_verified_at)}</span>}
            {!p.verified_ok && p.last_error && (
              <p className="mt-1 max-w-sm truncate text-xs text-destructive" data-testid="last-error" title={p.last_error}>
                {p.last_error}
              </p>
            )}
          </>
        )}
      </TableCell>
      {admin && (
        <TableCell>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <form onSubmit={test} className="flex items-center gap-1">
              <Input aria-label={`Model to test on ${p.name}`} placeholder="model id" value={model} onChange={(e) => setModel(e.target.value)} className="h-8 w-40 text-xs" />
              <Button type="submit" size="sm" variant="outline" disabled={busy || !model.trim()}>
                Test
              </Button>
            </form>
            <ProviderForm organizationId={organizationId} existing={p} onCreated={onChanged} />
            <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
              <DialogTrigger render={<Button size="sm" variant="outline" disabled={busy}>Delete</Button>} />
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete provider &quot;{p.name}&quot;?</DialogTitle>
                  <DialogDescription>Refused while any project&apos;s judge settings still route to it.</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button variant="destructive" disabled={busy} onClick={remove}>
                    Delete
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
          {result && (
            <p className="mt-1 text-right text-xs" data-testid="test-result">
              {result.ok ? (
                <span>
                  <Badge>ok</Badge> {result.model}
                  {result.latency_ms != null && <> · {ms(result.latency_ms)}</>} · {result.input_tokens}+{result.output_tokens} tokens
                </span>
              ) : (
                <span className="text-destructive">
                  <Badge variant="destructive">failed</Badge> {result.error}
                </span>
              )}
            </p>
          )}
        </TableCell>
      )}
    </TableRow>
  );
}

/** Create (no `existing`) or edit (key / base URL / timeout) a provider. The key field is write-only: blank keeps it. */
function ProviderForm({ organizationId, existing, onCreated }: { organizationId: string; existing?: Provider; onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(existing?.name ?? "");
  const [adapter, setAdapter] = useState<Adapter>(existing?.adapter ?? "openai");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(existing?.base_url ?? "");
  const [timeout, setTimeoutS] = useState(String(existing?.timeout_s ?? 60));
  const [clearKey, setClearKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const timeoutOk = Number(timeout) > 0 && Number(timeout) <= 600;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (existing) {
        const body: Record<string, unknown> = { base_url: baseUrl.trim() || null, timeout_s: Number(timeout) };
        if (clearKey) body.api_key = "";
        else if (apiKey) body.api_key = apiKey;
        await api(`/organizations/${organizationId}/providers/${existing.id}`, { method: "PATCH", body });
        toast.success(`Provider "${existing.name}" updated`);
      } else {
        await api(`/organizations/${organizationId}/providers`, {
          method: "POST",
          body: { name: name.trim(), adapter, api_key: apiKey || null, base_url: baseUrl.trim() || null, timeout_s: Number(timeout) },
        });
        toast.success(`Provider "${name.trim()}" added`);
        setName("");
      }
      setApiKey("");
      setClearKey(false);
      setOpen(false);
      onCreated();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  const id = existing ? `provider-${existing.id}` : "provider-new";

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={existing ? <Button size="sm" variant="outline">Edit</Button> : <Button>New provider</Button>} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{existing ? `Edit "${existing.name}"` : "New provider"}</DialogTitle>
          <DialogDescription>The key is encrypted at rest and never shown again.</DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="space-y-4">
          {!existing && (
            <>
              <div className="space-y-1">
                <Label htmlFor={`${id}-name`}>Name</Label>
                <Input id={`${id}-name`} required value={name} onChange={(e) => setName(e.target.value)} placeholder="openai, openrouter, ollama…" autoFocus />
              </div>
              <div className="space-y-1">
                <Label>Adapter</Label>
                <PickOne label="Adapter" value={adapter} items={ADAPTERS} onChange={(v) => setAdapter((v as Adapter) ?? "openai")} className="w-full" />
              </div>
            </>
          )}
          <div className="space-y-1">
            <Label htmlFor={`${id}-key`}>API key{existing ? " (blank keeps the current one)" : ""}</Label>
            <Input id={`${id}-key`} type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} disabled={clearKey} />
            {existing?.has_api_key && (
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={clearKey} onChange={(e) => setClearKey(e.target.checked)} /> Remove the stored key
              </label>
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${id}-url`}>Base URL (optional)</Label>
            <Input id={`${id}-url`} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://openrouter.ai/api/v1" />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${id}-timeout`}>Timeout (s)</Label>
            <Input id={`${id}-timeout`} type="number" min={1} max={600} value={timeout} onChange={(e) => setTimeoutS(e.target.value)} />
          </div>
          <Button type="submit" disabled={busy || !timeoutOk || (!existing && !name.trim())}>
            {existing ? "Save" : "Add provider"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
