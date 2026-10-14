"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAction } from "@/hooks/useAction";
import { api } from "@/lib/api";
import type { IngestKeyCreated } from "@/lib/types";

/** Mint an ingest key (one in flight at a time) and show the secret once; `onMinted` lets the page refresh its list. */
export function MintKeyForm({ projectId, onMinted }: { projectId: string; onMinted?: (key: IngestKeyCreated) => void }) {
  const [keyName, setKeyName] = useState("laptop");
  const [minted, setMinted] = useState<IngestKeyCreated | null>(null);
  const { busy, act } = useAction();
  const mint = async (e: React.FormEvent) => {
    e.preventDefault();
    const k = await act(`Key "${keyName.trim()}" created`, () => api<IngestKeyCreated>(`/projects/${projectId}/ingest-keys`, { method: "POST", body: { name: keyName.trim() } }), onMinted);
    if (k) setMinted(k);
  };
  return (
    <>
      <form onSubmit={mint} className="flex items-end gap-2">
        <div className="space-y-1">
          <Label htmlFor="key-name">Ingest key name</Label>
          <Input id="key-name" value={keyName} onChange={(e) => setKeyName(e.target.value)} className="w-56" />
        </div>
        <Button type="submit" variant="outline" disabled={busy || !keyName.trim()}>
          Create ingest key
        </Button>
      </form>
      {minted && (
        <div role="status" className="rounded-md border border-dashed p-3 text-sm">
          <p className="font-medium">Copy it now — it is shown once.</p>
          <code className="mt-1 block break-all text-xs" data-testid="minted-key">
            EVALSTONE_API_KEY={minted.key}
          </code>
        </div>
      )}
    </>
  );
}
