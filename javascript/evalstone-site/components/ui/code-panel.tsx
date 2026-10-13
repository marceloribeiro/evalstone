type Props = { title?: string; code: string; lang?: string };

/** A static code panel for the landing page (docs pages use Fumadocs' code blocks). */
export function CodePanel({ title, code }: Props) {
  return (
    <figure className="overflow-hidden rounded-xl border border-fd-border bg-stone-950 text-stone-100 shadow-lg">
      {title ? (
        <figcaption className="flex items-center gap-2 border-b border-stone-800 px-4 py-2 text-xs text-stone-400">
          <span className="size-2.5 rounded-full bg-stone-700" />
          <span className="size-2.5 rounded-full bg-stone-700" />
          <span className="size-2.5 rounded-full bg-stone-700" />
          <span className="ml-2 font-mono">{title}</span>
        </figcaption>
      ) : null}
      <pre className="overflow-x-auto p-4 text-[13px] leading-relaxed font-mono">
        <code>{code}</code>
      </pre>
    </figure>
  );
}
