/** The touchstone: a faceted stone with the streak real gold leaves on it, drawn as a tick (docs/img/logo.svg). */
export function StoneMark({ className = 'size-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" className={className}>
      <path d='M20 4 44 5 58 19 59 38 47 57 27 60 10 50 5 30 9 14Z' fill='#292524' stroke='#78716C' strokeWidth='1.4' strokeLinejoin='round' />
      <g strokeLinejoin='round' strokeWidth='.7'>
        <path d='M20 4 44 5 26 21 9 14Z' fill='#57534E' stroke='#57534E' />
        <path d='M44 5 58 19 41 29 26 21Z' fill='#44403C' stroke='#44403C' />
        <path d='M58 19 59 38 47 57 41 29Z' fill='#292524' stroke='#292524' />
        <path d='M47 57 27 60 31 43 41 29Z' fill='#1C1917' stroke='#1C1917' />
        <path d='M27 60 10 50 5 30 31 43Z' fill='#292524' stroke='#292524' />
        <path d='M5 30 9 14 26 21 31 43Z' fill='#3A3532' stroke='#3A3532' />
        <path d='M26 21 41 29 31 43Z' fill='#322D2A' stroke='#322D2A' />
      </g>
      <path d='M17 36.5 26.5 45.5 50 14.5' fill='none' stroke='#D97706' strokeWidth='5.2' strokeLinecap='round' strokeLinejoin='round' />
      <path d='M28.5 41.5 47 17' fill='none' stroke='#FCD34D' strokeWidth='1.3' strokeLinecap='round' opacity='.7' />
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
