import type { AlertPolicy } from "@/lib/types";
import { pct } from "@/lib/format";

export const METRIC_LABEL: Record<AlertPolicy["metric"], string> = { pass_rate: "pass rate", mean_score: "mean score" };

/** One rendering of a metric value everywhere: pass rate as a percentage, mean score to 3 places. */
export const metricValue = (metric: string, v: number) => (metric === "pass_rate" ? pct(v) : v.toFixed(3));

/** "pass rate ≥ 90.0% over 60 min (n ≥ 10)" */
export function policyText(p: AlertPolicy): string {
  const value = metricValue(p.metric, p.threshold);
  const window = p.window_minutes % 1440 === 0 ? `${p.window_minutes / 1440} d` : p.window_minutes % 60 === 0 ? `${p.window_minutes / 60} h` : `${p.window_minutes} min`;
  return `${METRIC_LABEL[p.metric]} ≥ ${value} over ${window} (n ≥ ${p.min_n})`;
}
