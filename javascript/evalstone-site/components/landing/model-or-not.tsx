import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Section } from '@/components/common/section';
import { CodePanel } from '@/components/ui/code-panel';

const YAML = `judges:
  default_model: anthropic/claude-haiku-5-5   # provider/model
providers:                                    # keys come from the environment
  anthropic: { api_key_env: ANTHROPIC_API_KEY }
  openai:    { api_key_env: OPENAI_API_KEY }  # or any OpenAI-compatible server:
  # openai:  { base_url: https://openrouter.ai/api/v1, api_key_env: OPENROUTER_API_KEY }
  # openai:  { base_url: http://localhost:11434/v1 }   # Ollama
  gemini:    { api_key_env: GEMINI_API_KEY }`;

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
          <div className="rounded-xl border border-fd-border bg-fd-card p-5">
            <h3 className="font-semibold">No model needed</h3>
            <ul className="mt-3 space-y-2 text-sm leading-relaxed text-fd-muted-foreground">
              {WITHOUT.map((item) => (
                <li key={item} className="flex gap-2">
                  <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-fd-foreground/50" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-fd-border bg-fd-card p-5">
            <h3 className="font-semibold">Needs a model, yours</h3>
            <ul className="mt-3 space-y-2 text-sm leading-relaxed text-fd-muted-foreground">
              {WITH.map((item) => (
                <li key={item} className="flex gap-2">
                  <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-accent-strong" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="space-y-4">
          <CodePanel title="evalstone.yaml" code={YAML} />
          <p className="text-sm leading-relaxed text-fd-muted-foreground">
            Three adapters: <code>openai</code> speaks the OpenAI Chat Completions API to api.openai.com
            or to any compatible server you point <code>base_url</code> at (OpenRouter, Ollama, vLLM,
            Groq), <code>anthropic</code> uses the official SDK, <code>gemini</code> calls Google&apos;s
            API. Keys are read from environment variables and never written to a config or a report.
            Verdicts are cached by content, so an unchanged output is never re-judged; every call is
            priced; a missing key or a failed call is an <strong>error, never a pass</strong>, and the
            gate fails on error rate.
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
