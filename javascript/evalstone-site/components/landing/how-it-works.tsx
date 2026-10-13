import { Section } from '@/components/common/section';
import { CodePanel } from '@/components/ui/code-panel';

const YAML = `# evalstone.yaml
project: support-bot
datasets:
  golden: evals/golden.jsonl
suites:
  nightly:
    dataset: golden
    target: { kind: http, url: http://localhost:8000/answer }
    checks: [json_schema, helpfulness, faithfulness]
    gate: { min_pass_rate: 0.95, max_regression: 0.02 }
judges:
  default_model: anthropic/claude-haiku-5-5
center:                      # optional — persists runs in PostgreSQL
  url: https://api.evalstone.com`;

const STEPS = [
  {
    title: 'Describe the suite',
    body: 'One YAML file: where the dataset is, what produces outputs (a function, an HTTP endpoint, a prompt), which checks to run, what the gate is.',
  },
  {
    title: 'Run it anywhere',
    body: 'evalstone run on your laptop, in pytest, in a GitHub Action, or from an MCP client. The judge scores quality with the model you name, on your key; cheap contract checks run first, so a broken output never reaches a paid call.',
  },
  {
    title: 'Keep the history',
    body: 'Point it at a center, self-hosted or ours, and every run lands in PostgreSQL: baselines, diffs, labels, calibrations, monitors.',
  },
];

export function HowItWorks() {
  return (
    <Section
      id="how-it-works"
      eyebrow="How it works"
      title="Three steps, no rewrite"
    >
      <div className="grid gap-10 lg:grid-cols-2 lg:items-start">
        <ol className="space-y-6">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex gap-4">
              <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-full border border-fd-border font-mono text-sm font-semibold">
                {i + 1}
              </span>
              <div>
                <h3 className="font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-fd-muted-foreground">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
        <CodePanel title="evalstone.yaml" code={YAML} />
      </div>
    </Section>
  );
}
