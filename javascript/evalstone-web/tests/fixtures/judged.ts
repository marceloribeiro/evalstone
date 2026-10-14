import { readFileSync } from "node:fs";
import { join } from "node:path";

const REPORT = JSON.parse(readFileSync(join(__dirname, "../../../../python/evalstone-api/tests/fixtures/rag-bot-ci-report.json"), "utf8"));
export const JUDGE_VERSION = "8d4f2a1b9c0e7f33";

type Result = { sample_id: string; output: unknown; score: Record<string, unknown>; [k: string]: unknown };

/** The sample report rewritten as one LLM-judge check `helpful` (mirrors the API's test helper). */
/**
 * `raw.model` is what the provider reports (a bare id); `raw.judge_model` is the routed `<provider>/<model>` the
 * center stamps and Promote pins (lib >= 0.2.3). They differ on purpose, so stamping the wrong one fails Promote.
 */
export function judgedReport(runId: string, opts: { judgeModel?: string; judgeFails?: string[]; judgeVersion?: string } = {}) {
  const r = JSON.parse(JSON.stringify(REPORT));
  r.id = runId;
  r.check_keys = ["helpful"];
  const seen = new Map<string, Result>();
  for (const res of r.results as Result[]) if (!seen.has(res.sample_id)) seen.set(res.sample_id, res);
  const fails = new Set(opts.judgeFails ?? []);
  r.results = [...seen.values()].map((res) => {
    const passed = !fails.has(res.sample_id);
    return {
      ...res,
      check_key: "helpful",
      score: {
        value: passed ? 0.75 : 0.25,
        passed,
        reason: passed ? "4/5" : "2/5",
        cost_usd: 0.0001,
        latency_ms: 10,
        error: null,
        skipped: false,
        raw: {
          model: "tiny-2026-10-01",
          judge_model: opts.judgeModel ?? "local/tiny",
          score: passed ? 4 : 2,
          scale: 5,
          judge_version: opts.judgeVersion ?? JUDGE_VERSION,
        },
      },
    };
  });
  r.summary.results = r.results.length;
  return r;
}
