import { Section } from '@/components/common/section';
import { FeatureCard } from '@/components/ui/feature-card';

export const LEARN_CHAPTERS = [
  { slug: 'what-are-evals', title: '1 · What are evals?', body: 'Tests for non-deterministic systems, and why "it looks fine" is not one.' },
  { slug: 'why-you-need-them', title: '2 · Why you need them', body: 'The regressions you did not see: model updates, prompt drift, and silent cost.' },
  { slug: 'the-eval-loop', title: '3 · The eval loop', body: 'Dataset → run → inspect → fix → re-run → gate. Small loop, run often.' },
  { slug: 'kinds-of-checks', title: '4 · Kinds of checks', body: 'Deterministic, LLM-as-judge, human, pairwise, RAG, agent trajectory, safety.' },
  { slug: 'building-a-golden-set', title: '5 · Building a golden set', body: 'Harvest, label, split, version. How big is big enough.' },
  { slug: 'llm-as-judge', title: '6 · LLM-as-judge done right', body: 'Rubrics, scales, position bias, calibration against humans, cost control.' },
  { slug: 'gates-and-ci', title: '7 · Gates and CI', body: 'Thresholds, baselines, flakiness, and what to actually block on.' },
  { slug: 'evals-in-production', title: '8 · Evals in production', body: 'Sampling, monitors, drift, and avoiding alert fatigue.' },
  { slug: 'pitfalls', title: '9 · Pitfalls', body: 'Overfitting the golden set, leaking answers, judge collusion, green-but-broken.' },
];

export function LearnCards() {
  return (
    <Section
      id="learn"
      eyebrow="Learning center"
      title="Evals 101, nine short chapters"
      lead="Written for people who ship LLM features and have never run an eval. Each chapter explains why, shows the pitfall, then the practice. Read in order or jump in."
      tone="muted"
    >
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {LEARN_CHAPTERS.map((c) => (
          <FeatureCard key={c.slug} title={c.title} href={`/docs/learn/${c.slug}`}>
            {c.body}
          </FeatureCard>
        ))}
      </div>
    </Section>
  );
}
