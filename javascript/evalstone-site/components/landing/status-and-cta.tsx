import { GithubIcon } from '@/components/common/github-icon';
import { Container } from '@/components/common/container';
import { ButtonLink } from '@/components/ui/button-link';
import { githubUrl } from '@/lib/shared';

export function StatusAndCta() {
  return (
    <section className="py-16 sm:py-24" aria-labelledby="status-title">
      <Container>
        <div className="rounded-2xl border border-fd-border bg-fd-card p-8 sm:p-12">
          <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-accent-strong dark:text-accent">
            Status
          </p>
          <h2 id="status-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Built in the open, in this order
          </h2>
          <ol className="mt-6 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <li className="rounded-lg border border-fd-border p-4">
              <span className="font-mono text-xs text-pass">live</span>
              <p className="mt-1 font-medium">Site + learning center</p>
            </li>
            <li className="rounded-lg border border-fd-border p-4">
              <span className="font-mono text-xs text-pass">live</span>
              <p className="mt-1 font-medium">Library + CLI on PyPI</p>
            </li>
            <li className="rounded-lg border border-fd-border p-4">
              <span className="font-mono text-xs text-pass">live</span>
              <p className="mt-1 font-medium">MCP server · pytest · labeling · GitHub Action</p>
            </li>
            <li className="rounded-lg border border-fd-border p-4">
              <span className="font-mono text-xs text-fd-muted-foreground">next</span>
              <p className="mt-1 font-medium">Center: API + web, self-hosted or hosted</p>
            </li>
          </ol>
          <p className="mt-6 max-w-2xl text-fd-muted-foreground">
            The roadmap, the design decisions and every commit are public. Star the repository to follow
            along, or open an issue with the eval problem you are stuck on; that is how the chapters get
            better.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href={githubUrl} external>
              <GithubIcon />
              Follow on GitHub
            </ButtonLink>
            <ButtonLink href="/docs/evalstone" variant="secondary">
              Read the docs
            </ButtonLink>
          </div>
        </div>
      </Container>
    </section>
  );
}
