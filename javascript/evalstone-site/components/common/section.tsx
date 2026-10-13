import type { ReactNode } from 'react';
import { Container } from './container';

type SectionProps = {
  id?: string;
  eyebrow?: string;
  title: string;
  lead?: ReactNode;
  children?: ReactNode;
  tone?: 'default' | 'muted';
};

export function Section({ id, eyebrow, title, lead, children, tone = 'default' }: SectionProps) {
  return (
    <section
      id={id}
      className={`scroll-mt-14 py-16 sm:py-24 ${tone === 'muted' ? 'bg-fd-muted/60' : ''}`}
      aria-labelledby={id ? `${id}-title` : undefined}
    >
      <Container>
        <div className="max-w-3xl">
          {eyebrow ? (
            <p className="mb-3 text-sm font-semibold uppercase tracking-wider text-accent-strong dark:text-accent">
              {eyebrow}
            </p>
          ) : null}
          <h2 id={id ? `${id}-title` : undefined} className="text-3xl font-semibold tracking-tight sm:text-4xl">
            {title}
          </h2>
          {lead ? <div className="mt-4 text-lg text-fd-muted-foreground">{lead}</div> : null}
        </div>
        {children ? <div className="mt-10">{children}</div> : null}
      </Container>
    </section>
  );
}
