"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

/** Tags as chips; with `onChange` (admins) each chip has a remove button and an input adds one on Enter. */
export function TagChips({ tags, onChange, busy }: { tags: string[]; onChange?: (tags: string[]) => void; busy?: boolean }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const t = draft.trim();
    if (!t || tags.includes(t)) return setDraft("");
    onChange?.([...tags, t]);
    setDraft("");
  };
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="tags">
      <ul className="contents" aria-label="Tags">
        {tags.map((t) => (
          <li key={t}>
            <Badge variant="outline" className="gap-1">
              {t}
              {onChange && (
                <button type="button" aria-label={`Remove tag ${t}`} disabled={busy} onClick={() => onChange(tags.filter((x) => x !== t))} className="rounded hover:bg-muted">
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          </li>
        ))}
      </ul>
      {onChange && (
        <Input
          aria-label="Add tag"
          placeholder="add tag…"
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          onBlur={add}
          className="h-7 w-32 text-xs"
        />
      )}
      {tags.length === 0 && !onChange && <span className="text-xs text-muted-foreground">no tags</span>}
    </div>
  );
}
