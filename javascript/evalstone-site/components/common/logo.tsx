export function StoneMark({ className = 'size-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={className}>
      <path
        d="M9 3h14l6 9-6 17H9L3 12z"
        className="fill-stone-800 dark:fill-stone-200"
      />
      <path d="M9.5 19.5 20 9.5" className="stroke-accent" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2 font-semibold tracking-tight">
      <StoneMark />
      <span>Evalstone</span>
    </span>
  );
}
