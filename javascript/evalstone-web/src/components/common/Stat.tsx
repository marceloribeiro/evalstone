/** A labelled number tile for a page's summary row (`<dl aria-label=…>` wraps them). */
export function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={`text-lg font-semibold ${warn ? "text-destructive" : ""}`}>{value}</dd>
    </div>
  );
}
