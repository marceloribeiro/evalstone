import { Blocks, BookOpen, Cpu, GitPullRequest, Plug, Radar, Users, Scale } from 'lucide-react';
import { Section } from '@/components/common/section';
import { FeatureCard } from '@/components/ui/feature-card';

export function HowItHelps() {
  return (
    <Section
      id="how-it-helps"
      eyebrow="How Evalstone helps"
      title="One layer, from the first golden set to production monitoring"
      lead="Everything is designed to be plugged into an existing project with no rewrite: a pip install, a YAML file, and a base of checks you extend in plain Python."
      tone="muted"
    >
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <FeatureCard icon={<BookOpen className="size-5" />} title="Learning center" href="/docs/learn" status="live">
          A short course on evals: what they are, why they matter, the kinds of checks, judges, gates,
          production, and the pitfalls. Read it before you write a single test.
        </FeatureCard>
        <FeatureCard icon={<Blocks className="size-5" />} title="Library" href="/docs/evalstone/library" status="live">
          Datasets, checks, suites, runs and gates as plain Python. Deterministic checks, LLM judges,
          RAG, safety, pairwise and agent-trajectory checks built in.
        </FeatureCard>
        <FeatureCard icon={<Users className="size-5" />} title="Training center" href="/docs/evalstone/center" status="live">
          Versioned golden sets harvested from real traffic, a human labeling queue, and judge
          calibration so your LLM judge agrees with your people.
        </FeatureCard>
        <FeatureCard icon={<Scale className="size-5" />} title="Check center" href="/docs/evalstone/center" status="live">
          Run history with baselines and diffs, a catalog of reusable checks, and alerts when a
          monitor sees quality drift.
        </FeatureCard>
        <FeatureCard icon={<GitPullRequest className="size-5" />} title="CI gate" href="/docs/learn/gates-and-ci" status="live">
          A GitHub Action and a pytest plugin. A pull request that lowers the pass rate or regresses
          the baseline goes red.
        </FeatureCard>
        <FeatureCard icon={<Radar className="size-5" />} title="Production monitoring" href="/docs/learn/evals-in-production" status="live">
          Sample live exchanges, score them continuously, and see the trend. Works with any proxy or
          SDK that can post a trace.
        </FeatureCard>
        <FeatureCard icon={<Plug className="size-5" />} title="API" href="/docs/evalstone/center" status="live">
          Everything the center does is a REST endpoint with OpenAPI docs, so other languages and
          other tools can push runs and read results.
        </FeatureCard>
        <FeatureCard icon={<Cpu className="size-5" />} title="MCP server" href="/docs/evalstone/mcp" status="live">
          Let Claude Code, Cursor or any MCP client run a suite, judge an output or record a sample
          while you work.
        </FeatureCard>
      </div>
    </Section>
  );
}
