import type { ReactNode } from 'react';
import Link from 'next/link';

type Props = { icon?: ReactNode; title: string; children: ReactNode; href?: string; status?: string };

export function FeatureCard({ icon, title, children, href, status }: Props) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {icon ? <span className="text-accent-strong dark:text-accent">{icon}</span> : null}
          <h3 className="font-semibold">{title}</h3>
        </div>
        {status ? (
          <span className="rounded-full border border-fd-border px-2 py-0.5 text-[11px] uppercase tracking-wide text-fd-muted-foreground">
            {status}
          </span>
        ) : null}
      </div>
      <div className="mt-3 text-sm leading-relaxed text-fd-muted-foreground">{children}</div>
    </>
  );
  const className =
    'block rounded-xl border border-fd-border bg-fd-card p-5 transition-colors hover:border-accent/60';
  return href ? (
    <Link href={href} className={className}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}
