import Link from "next/link";
import { Gem } from "lucide-react";
import { cn } from "@/lib/utils";

/** Wordmark; `mark` = icon only for the collapsed sidebar. */
export function Brand({ mark = false, href = "/organizations", className }: { mark?: boolean; href?: string | null; className?: string }) {
  const inner = (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <Gem className="size-5 text-primary" aria-hidden />
      {!mark && <span>Evalstone</span>}
    </span>
  );
  return href ? (
    <Link href={href} title="All organizations">
      {inner}
    </Link>
  ) : (
    inner
  );
}
