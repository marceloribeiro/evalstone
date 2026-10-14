import { ArrowRight, BookOpen } from 'lucide-react';
import { GithubIcon } from '@/components/common/github-icon';
import { Container } from '@/components/common/container';
import { ButtonLink } from '@/components/ui/button-link';
import { CodePanel } from '@/components/ui/code-panel';
import { githubUrl } from '@/lib/shared';

const HERO_CODE = `import evalstone as es

suite = es.Suite(
    "support-bot",
    dataset=es.Dataset.from_jsonl("evals/golden.jsonl"),
    checks=[
        es.checks.json_schema(schema=Answer),
        es.checks.judge("helpfulness", rubric=RUBRIC),
        es.checks.rag.faithfulness(),
    ],
    gate=es.Gate(min_pass_rate=0.95),
)

run = suite.run(target=answer)   # your function
suite.enforce(run)               # raises GateFailed → red in CI`;

export function Hero() {
  return (
    <section className="relative overflow-hidden" aria-labelledby="hero-title">
      <div className="landing-grid pointer-events-none absolute inset-0 text-stone-900 dark:text-stone-100" />
      <Container className="relative grid gap-12 py-20 sm:py-28 lg:grid-cols-2 lg:items-center">
        <div>
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-fd-border bg-fd-background px-3 py-1 text-xs font-medium text-fd-muted-foreground">
            <span className="size-1.5 rounded-full bg-accent" />
            Open source · MIT · built in the open
          </p>
          <h1 id="hero-title" className="text-4xl font-semibold tracking-tight sm:text-5xl lg:text-6xl">
            Know your LLM feature works <span className="text-accent-strong dark:text-accent">before</span> your
            users do.
          </h1>
          <p className="mt-6 max-w-xl text-lg text-fd-muted-foreground">
            Evalstone is the plug-and-play evals layer for any LLM-based project: a Python library, a
            learning center, a check center, an API and an MCP server. First it teaches you what evals
            are. Then it runs them for you, in CI and in production.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/docs/learn">
              <BookOpen className="size-4" />
              Start with Evals 101
            </ButtonLink>
            <ButtonLink href="/docs/evalstone" variant="secondary">
              How Evalstone helps
              <ArrowRight className="size-4" />
            </ButtonLink>
            <ButtonLink href={githubUrl} variant="secondary" external>
              <GithubIcon />
              GitHub
            </ButtonLink>
          </div>
        </div>
        <CodePanel title="evals/support_bot.py" code={HERO_CODE} />
      </Container>
    </section>
  );
}
