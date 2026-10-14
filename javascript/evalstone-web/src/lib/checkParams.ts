import type { CheckParam } from "@/lib/types";

/** The widget a factory param gets, from its annotation (the API mirrors the library's signature). */
export type Widget = "bool" | "number" | "list" | "json" | "text";

export function widgetFor(p: CheckParam): Widget {
  const a = p.annotation;
  if (p.machine_bound === "target") return "json";
  if (/\bbool\b/.test(a) && !/str/.test(a)) return "bool";
  if (/\b(int|float)\b/.test(a) && !/str|Any|dict/.test(a)) return "number";
  if (/Iterable|list|Sequence/.test(a)) return "list";
  if (/dict|Mapping|Any\b|type\b|schema/i.test(a)) return "json";
  return "text";
}

/** What the form shows for a stored (or default) value. */
export function toField(widget: Widget, value: unknown): string {
  if (value === null || value === undefined) return "";
  if (widget === "bool") return value ? "true" : "false";
  if (widget === "list") return Array.isArray(value) ? value.join(", ") : String(value);
  if (widget === "json") return typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return String(value);
}

/** Parse one field back into the param's JSON value; `undefined` = leave the param out (use the default). */
export function fromField(widget: Widget, raw: string): { value?: unknown; error?: string } {
  const s = raw.trim();
  if (widget === "bool") return { value: s === "true" };
  if (s === "") return {};
  if (widget === "number") {
    const n = Number(s);
    return Number.isFinite(n) ? { value: n } : { error: "not a number" };
  }
  if (widget === "list") return { value: s.split(",").map((x) => x.trim()).filter(Boolean) };
  if (widget === "json") {
    try {
      return { value: JSON.parse(s) };
    } catch {
      return { error: "not valid JSON" };
    }
  }
  return { value: s };
}

/** Build the `params` object from the form's fields; collects per-field errors and missing required params. */
export function buildParams(params: CheckParam[], fields: Record<string, string>): { params: Record<string, unknown>; errors: Record<string, string> } {
  const out: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  for (const p of params) {
    if (p.machine_bound === "callable") continue; // not storable: the library binds it on the machine
    const widget = widgetFor(p);
    const { value, error } = fromField(widget, fields[p.name] ?? "");
    if (error) errors[p.name] = error;
    else if (value === undefined) {
      if (p.required) errors[p.name] = "required";
    } else if (JSON.stringify(value) === JSON.stringify(widget === "bool" ? (p.default ?? false) : p.default)) {
      // a param at its factory default is left out, so the stored params stay as minimal as hand-written YAML
    } else out[p.name] = value;
  }
  return { params: out, errors };
}
