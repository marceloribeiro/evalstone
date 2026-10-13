import { ArrowLink } from '@/components/common/arrow-link';
import { Section } from '@/components/common/section';
import { CodePanel } from '@/components/ui/code-panel';

const YAML = `checks:
  helpful:
    type: judge                                 # the quality signal
    rubric: |
      Answers the question from the policy; states the concrete rule;
      invents nothing that is not in the policy.
    scale: 5                                    # pass at 4
judges:
  default_model: anthropic/claude-haiku-5-5     # provider/model; switch here, or per check
  # default_model: openai/anthropic/claude-haiku-5-5   # the same model through OpenRouter
providers:                                      # keys come from the environment
  anthropic: { api_key_env: ANTHROPIC_API_KEY }
  openai:    { base_url: https://openrouter.ai/api/v1, api_key_env: OPENROUTER_API_KEY }
  gemini:    { api_key_env: GEMINI_API_KEY }`;

const JUDGE = [
  'A rubric on a small scale, graded by the model you name; the verdict is a level and a reason, as JSON',
  'rag.faithfulness, rag.context_relevance, rag.answer_relevance: judges with fixed rubrics',
  'comparison.pairwise: which of two outputs is better, both orders, so position bias cancels',
  'Measured against human labels: a judge you have not checked is an opinion (the agreement report is on the roadmap, in Evalstone Center)',
  'No key, a refusal, malformed JSON: an error, never a pass, and the gate fails on error rate',
];

const HUMAN = [
  'evalstone label grades outputs in the terminal, resumably, keyed by sample and output',
  'The human check scores from those labels; they are the ground truth judges are calibrated against',
];

const CONTRACTS = [
  'JSON schema, must-include facts, regex, length, numeric tolerance',
  'Safety rules (refusal, PII, forbidden phrases) and agent-trajectory checks',
  'Exact and free; deterministic and trajectory checks run before the judges in every suite',
];

function BulletCard({
  title,
  kicker,
  items,
  dot,
  className = '',
}: {
  title: string;
  kicker: string;
  items: string[];
  dot: string;
  className?: string;
}) {
  return (
    <div className={`rounded-xl border border-fd-border bg-fd-card p-5 ${className}`}>
      <p className="text-xs font-semibold uppercase tracking-wider text-fd-muted-foreground">{kicker}</p>
      <h3 className="mt-1 font-semibold">{title}</h3>
      <ul className="mt-3 space-y-2 text-sm leading-relaxed text-fd-muted-foreground">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span aria-hidden className={`mt-2 size-1.5 shrink-0 rounded-full ${dot}`} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ModelOrNot() {
  return (
    <Section
      id="model-or-not"
      eyebrow="Where the model comes in"
      title="Quality is judged by a model you choose. Contracts are checked exactly. Humans are the ground truth."
      lead={
        <>
          Three layers, and the judge is where quality gets measured: a rubric, a small scale, a model
          you name, checked against labels people wrote. Around it, deterministic checks catch the
          contract failures exactly and for free. The judge calls your provider directly, with your
          key; there is no Evalstone account, proxy or relay in the path.
        </>
      }
    >
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-6">
          <BulletCard
            kicker="1 · the quality signal"
            title="LLM-as-judge, with your model"
            items={JUDGE}
            dot="bg-accent-strong"
            className="border-accent-strong/40"
          />
          <BulletCard kicker="2 · the ground truth" title="Human labels" items={HUMAN} dot="bg-accent-strong" />
          <BulletCard
            kicker="3 · the guardrails"
            title="Deterministic checks, no model needed"
            items={CONTRACTS}
            dot="bg-fd-foreground/50"
          />
        </div>
        <div className="space-y-4">
          <CodePanel title="evalstone.yaml" code={YAML} />
          <p className="text-sm leading-relaxed text-fd-muted-foreground">
            Three native adapters: <code>anthropic</code> through the official SDK, <code>gemini</code>{' '}
            through Google&apos;s API, and <code>openai</code>, which speaks the Chat Completions API to
            api.openai.com or to any compatible server you point <code>base_url</code> at, so OpenRouter
            gives you every model it hosts and Ollama runs one locally. Switching the judge is one line
            (<code>default_model</code>, or <code>model:</code> on a single check). Keys are read from
            environment variables and never written to a report. Verdicts are cached by content for
            the life of the process; calls to models in the price table are priced; a missing key or a
            failed call is an <strong>error, never a pass</strong>.
          </p>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <ArrowLink href="/docs/evalstone/how-it-works">How Evalstone works, in full</ArrowLink>
            <ArrowLink href="/docs/learn/llm-as-judge">Why judges need calibrating (Evals 101, ch. 6)</ArrowLink>
          </div>
        </div>
      </div>
    </Section>
  );
}
