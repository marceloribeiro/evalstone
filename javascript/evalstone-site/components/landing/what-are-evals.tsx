import { ArrowLink } from '@/components/common/arrow-link';
import { Section } from '@/components/common/section';

const STEPS = [
  { n: '1', title: 'Dataset', body: 'A set of inputs with, where possible, what a good answer looks like. Real traffic, hand-written, or synthetic.' },
  { n: '2', title: 'Run', body: 'Send every input through your feature and keep the outputs. Pin the dataset version and the git commit.' },
  { n: '3', title: 'Check', body: 'Score each output: deterministic rules, an LLM judge with a rubric, a human, or a comparison against another run.' },
  { n: '4', title: 'Gate', body: 'Turn scores into a decision: pass rate above a threshold, no regression versus the baseline, cost under budget.' },
];

export function WhatAreEvals() {
  return (
    <Section
      id="what-are-evals"
      eyebrow="Evals, in one minute"
      title="An eval is a test for a system that does not give the same answer twice"
      lead={
        <>
          Unit tests assert equality. Evals measure quality over a dataset and decide whether the
          number is good enough. The loop is small, and it is the same loop whether you are grading a
          chatbot, a RAG pipeline, an extraction prompt or an agent.
        </>
      }
    >
      <ol className="grid gap-6 md:grid-cols-4">
        {STEPS.map((s) => (
          <li key={s.n} className="relative rounded-xl border border-fd-border bg-fd-card p-5">
            <span className="mb-3 inline-flex size-8 items-center justify-center rounded-full bg-accent-soft font-mono text-sm font-semibold text-accent-strong">
              {s.n}
            </span>
            <h3 className="font-semibold">{s.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-fd-muted-foreground">{s.body}</p>
          </li>
        ))}
      </ol>
      <ArrowLink href="/docs/learn/what-are-evals" className="mt-8 gap-2 text-base">
        Read the full chapter
      </ArrowLink>
    </Section>
  );
}
