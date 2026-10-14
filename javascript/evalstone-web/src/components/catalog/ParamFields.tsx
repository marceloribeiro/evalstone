"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { widgetFor } from "@/lib/checkParams";
import type { CheckParam } from "@/lib/types";

/** One field per factory param, typed by its annotation; callables are shown as not storable. */
export function ParamFields({ params, fields, errors, onChange, idPrefix }: { params: CheckParam[]; fields: Record<string, string>; errors: Record<string, string>; onChange: (name: string, value: string) => void; idPrefix: string }) {
  if (params.length === 0) return <p className="text-xs text-muted-foreground">This check type takes no parameters.</p>;
  return (
    <div className="space-y-3">
      {params.map((p) => {
        const widget = widgetFor(p);
        const id = `${idPrefix}-${p.name}`;
        const hint =
          p.machine_bound === "callable"
            ? "a Python callable — bound in the library, not storable here"
            : p.machine_bound === "path"
              ? "a file on a machine; only \"center\" is storable"
              : p.machine_bound === "target"
                ? "a target spec (JSON)"
                : p.falls_back_to_expected
                  ? `${p.annotation} — leave empty to compare against the sample's expected`
                  : p.annotation;
        return (
          <div key={p.name} className="space-y-1">
            <Label htmlFor={id} className="font-mono text-xs">
              {p.name}
              {p.required && <span className="ml-1 text-destructive">*</span>}
              <span className="ml-2 font-sans text-muted-foreground">{hint}</span>
            </Label>
            {p.machine_bound === "callable" ? (
              <Input id={id} disabled value="" placeholder="not storable" />
            ) : widget === "bool" ? (
              <label className="flex items-center gap-2 text-sm">
                <input id={id} type="checkbox" checked={(fields[p.name] ?? (p.default ? "true" : "false")) === "true"} onChange={(e) => onChange(p.name, e.target.checked ? "true" : "false")} />
                {p.name}
              </label>
            ) : widget === "tristate" ? (
              <select id={id} value={fields[p.name] ?? ""} onChange={(e) => onChange(p.name, e.target.value)} className="h-9 rounded-md border bg-background px-2 text-sm">
                <option value="">unset (the check decides)</option>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : widget === "json" ? (
              <Textarea id={id} rows={3} value={fields[p.name] ?? ""} onChange={(e) => onChange(p.name, e.target.value)} className="font-mono text-xs" placeholder={p.default == null ? "a value, or JSON for objects and lists" : JSON.stringify(p.default)} />
            ) : widget === "list" ? (
              <Textarea id={id} rows={3} value={fields[p.name] ?? ""} onChange={(e) => onChange(p.name, e.target.value)} className="font-mono text-xs" placeholder={"one item per line"} />
            ) : (
              <Input
                id={id}
                type={widget === "number" || widget === "int" ? "number" : "text"}
                step={widget === "int" ? 1 : widget === "number" ? "any" : undefined}
                value={fields[p.name] ?? ""}
                onChange={(e) => onChange(p.name, e.target.value)}
                className={widget === "number" || widget === "int" ? "w-40" : undefined}
                placeholder={p.default == null ? "" : String(p.default)}
              />
            )}
            {errors[p.name] && (
              <p className="text-xs text-destructive" role="alert">
                {errors[p.name]}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
