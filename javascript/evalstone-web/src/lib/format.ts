/** Display helpers shared by the data pages. */
export const pct = (x: number, digits = 1) => `${(x * 100).toFixed(digits)}%`;
export const usd = (x: number) => (x === 0 ? "$0" : x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(2)}`);
export const ms = (x: number) => (x >= 1000 ? `${(x / 1000).toFixed(1)} s` : `${x.toFixed(0)} ms`);
export const when = (iso: string) => new Date(iso).toLocaleString();
export const signed = (x: number, fmt: (v: number) => string) => (x > 0 ? `+${fmt(x)}` : fmt(x));
/** A short, stable rendering of any JSON value for a table cell. */
export function brief(v: unknown, max = 160): string {
  const s = typeof v === "string" ? v : v == null ? "" : JSON.stringify(v);
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
