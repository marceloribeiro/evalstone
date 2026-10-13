import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Section } from '@/components/common/section';
import { CodePanel } from '@/components/ui/code-panel';

const YAML = `judges:
  default_model: anthropic/claude-haiku-5-5   # provider/model
providers:                                    # keys come from the environment
  anthropic: { api_key_env: ANTHROPIC_API_KEY }
  openai:    { api_key_env: OPENAI_API_KEY }
  gemini:    { api_key_env: GEMINI_API_KEY }

# The openai adapter speaks to any OpenAI-compatible server. Replace the
# openai line above with one of these (one \`openai:\` entry per file):
#   openai: { base_url: https://openrouter.ai/api/v1, api_key_env: OPENROUTER_API_KEY }
#   openai: { base_url: http://localhost:11434/v1 }   # Ollama, no key`;

const WITHOUT = [
  'Deterministic checks: exact, contains, regex, JSON schema, length, numeric tolerance',
  'Safety rules (refusal, PII, forbidden phrases) and agent-trajectory checks',
  'Human labels: evalstone label in the terminal, the human check in the suite',
  'Datasets, recorded or live targets, suites, gates, reports, run comparison',
  'The CLI, the pytest plugin, the GitHub Action and the MCP server',
];

const WITH = [
  'judge: a rubric on a small scale, graded by the model you name',
  'rag.faithfulness, rag.context_relevance, rag.answer_relevance: judges with fixed rubrics',
  'comparison.pairwise: a judge choosing between two outputs, both orders',
  'A prompt target, when the thing under test is a prompt run through a model',
];

function BulletCard({ title, items, dot }: { title: string; items: string[]; dot: string }) {
  return (
    <div className="rounded-xl border border-fd-border bg-fd-card p-5">
      <h3 className="font-semibold">{title}</h3>
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
      title="Most of it runs with no model at all. Judges call your provider, with your key."
      lead={
        <>
          The quickstart&apos;s first run uses recorded outputs and deterministic checks: nothing is
          called. Add an LLM-as-judge check and Evalstone calls the provider you name, directly from
          your machine or CI. There is no Evalstone account, proxy or relay in the path.
        </>
      }
    >
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-6">
          <BulletCard title="No model needed" items={WITHOUT} dot="bg-fd-foreground/50" />
          <BulletCard title="Needs a model, yours" items={WITH} dot="bg-accent-strong" />
        </div>
        <div className="space-y-4">
          <CodePanel title="evalstone.yaml" code={YAML} />
          <p className="text-sm leading-relaxed text-fd-muted-foreground">
            Three adapters: <code>openai</code> speaks the OpenAI Chat Completions API to api.openai.com
            or to any compatible server you point <code>base_url</code> at (OpenRouter, Ollama, vLLM,
            Groq), <code>anthropic</code> uses the official SDK, <code>gemini</code> calls Google&apos;s
            API. Keys are read from environment variables by default and never written to a report.
            Verdicts are cached by content for the life of the process (the MCP server keeps its cache
            for the whole session); a cache shared across runs comes with the center. Calls to models in
            the built-in price table (Claude today) are priced, others are reported unpriced until you
            add them under <code>prices:</code>. A missing key or a failed call is an{' '}
            <strong>error, never a pass</strong>, and the gate fails on error rate.
          </p>
          <Link
            href="/docs/evalstone/how-it-works"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-accent-strong hover:underline dark:text-accent"
          >
            How Evalstone works, in full
            <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
      </div>
    </Section>
  );
}
