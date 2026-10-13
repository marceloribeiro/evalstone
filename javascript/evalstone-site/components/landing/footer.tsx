import Link from 'next/link';
import { Container } from '@/components/common/container';
import { Logo } from '@/components/common/logo';
import { githubUrl } from '@/lib/shared';

export function Footer() {
  return (
    <footer className="border-t border-fd-border py-10 text-sm text-fd-muted-foreground">
      <Container className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-2">
          <Logo />
          <p>The evals layer for LLM products. Open source, MIT.</p>
        </div>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2">
          <Link href="/docs/learn" className="hover:text-fd-foreground">Learn</Link>
          <Link href="/docs/evalstone" className="hover:text-fd-foreground">Evalstone</Link>
          <a href={githubUrl} className="hover:text-fd-foreground" target="_blank" rel="noreferrer">GitHub</a>
          <a href={`${githubUrl}/blob/main/docs/ROADMAP.md`} className="hover:text-fd-foreground" target="_blank" rel="noreferrer">Roadmap</a>
        </nav>
      </Container>
    </footer>
  );
}
