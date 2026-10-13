import { Section } from '@/components/common/section';

const PAINS = [
  {
    title: '"It looks fine" is not a test',
    body: 'You tweak a prompt, try three questions, and ship. The fourth question, the one a customer asks, is the one that broke. Non-deterministic systems need a repeatable answer to "is it better?".',
  },
  {
    title: 'Model updates move the floor',
    body: 'Providers retire and replace models. The same prompt gives different answers next month. Without a golden set and a baseline run you only find out from support tickets.',
  },
  {
    title: 'A judge you never measured is a guess',
    body: 'LLM-as-judge is powerful and cheap, and it is also biased, position-sensitive and happy to agree with itself. A judge earns trust by being calibrated against humans.',
  },
  {
    title: 'Production is the eval nobody runs',
    body: 'Offline suites catch regressions you anticipated. Real traffic finds the rest. Sampling and scoring live exchanges turns "we think it is fine" into a number with a trend.',
  },
];

export function Problem() {
  return (
    <Section
      id="problem"
      eyebrow="The problem"
      title="Shipping LLM features by vibes works until it doesn't"
      lead="Every team that puts a model in front of users hits the same four walls."
      tone="muted"
    >
      <div className="grid gap-6 sm:grid-cols-2">
        {PAINS.map((p) => (
          <div key={p.title} className="rounded-xl border border-fd-border bg-fd-card p-6">
            <h3 className="font-semibold">{p.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-fd-muted-foreground">{p.body}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}
