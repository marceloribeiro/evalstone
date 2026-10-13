import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

/** The landing page's inline "read more" link: text, then an arrow. */
export function ArrowLink({
  href,
  children,
  className,
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        'inline-flex items-center gap-1.5 text-sm font-medium text-accent-strong hover:underline dark:text-accent',
        className,
      )}
    >
      {children}
      <ArrowRight className="size-4" aria-hidden />
    </Link>
  );
}
