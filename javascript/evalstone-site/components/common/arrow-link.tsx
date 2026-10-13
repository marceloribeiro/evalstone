import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { ReactNode } from 'react';

/** The landing page's inline "read more" link: text, then an arrow. */
export function ArrowLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-accent-strong hover:underline dark:text-accent"
    >
      {children}
      <ArrowRight className="size-4" aria-hidden />
    </Link>
  );
}
