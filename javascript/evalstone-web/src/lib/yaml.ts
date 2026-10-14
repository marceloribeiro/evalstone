/** A small YAML emitter for the shapes the center exchanges (the `checks:` block): scalars, lists, maps. */
export function toYaml(value: unknown, indent = 0): string {
  const pad = "  ".repeat(indent);
  if (Array.isArray(value)) {
    if (value.length === 0) return " []";
    return "\n" + value.map((v) => `${pad}- ${isScalar(v) ? scalar(v) : toYaml(v, indent + 1).trimStart()}`).join("\n");
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return " {}";
    return "\n" + entries.map(([k, v]) => `${pad}${key(k)}:${isScalar(v) ? " " + scalar(v) : toYaml(v, indent + 1)}`).join("\n");
  }
  return " " + scalar(value);
}

/** The `checks:` block as users paste it into evalstone.yaml. */
export const checksYaml = (checks: Record<string, Record<string, unknown>>) => `checks:${toYaml(checks, 1)}\n`;

const isScalar = (v: unknown) => v === null || v === undefined || ["string", "number", "boolean"].includes(typeof v);
const key = (k: string) => (/^[A-Za-z_][\w.-]*$/.test(k) ? k : JSON.stringify(k));
function scalar(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "boolean" || typeof v === "number") return String(v);
  const s = String(v);
  // quote what YAML would otherwise reinterpret (numbers, booleans, null, leading/trailing space, special chars)
  return /^[A-Za-z][\w .,/()'-]*$/.test(s) && !/^(true|false|null|yes|no|on|off)$/i.test(s) && s === s.trim() ? s : JSON.stringify(s);
}
