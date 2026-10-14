import Image from 'next/image';
import { Section } from '@/components/common/section';

const SHOTS = [
  {
    src: '/media/run.png',
    alt: 'A judged run in the center: per-check pass rates, the failed gate, and the judge reason for every verdict',
    title: 'A run',
    body: 'Per-check results, the gate the CLI enforced, and the judge’s reason for every verdict.',
  },
  {
    src: '/media/labeler.png',
    alt: 'The labeler: input, expected, output and the machine verdict, with 1–5 grade buttons and keyboard hints',
    title: 'Labeling',
    body: 'People grade outputs from the keyboard: 1–5, N for notes, S to skip, Enter to submit.',
  },
  {
    src: '/media/calibration.png',
    alt: 'The Judges page: judge settings, the judge versions seen, and a finished calibration with agreement, kappa and a Promote button',
    title: 'Calibration',
    body: 'The judge measured against those labels (agreement, Cohen’s kappa), then promoted.',
  },
];

export function SeeIt() {
  return (
    <Section
      id="see-it"
      eyebrow="See it"
      title="One minute, end to end"
      lead={
        <>
          The CLI catches a regression on a fresh project; then a center grades the judge against people
          and promotes it. Recorded from real commands and a center running locally.
        </>
      }
    >
      <figure>
        <video
          className="w-full rounded-xl border border-fd-border shadow-sm"
          src="/media/walkthrough.mp4"
          poster="/media/walkthrough-poster.jpg"
          width={1280}
          height={720}
          autoPlay
          muted
          loop
          playsInline
          controls
          preload="metadata"
          aria-label="Walkthrough: evalstone init, a gate that fails on a regression and passes after the fix, then labeling, calibrating and promoting a judge in the center"
        />
        <figcaption className="mt-3 text-sm text-fd-muted-foreground">
          <code>evalstone init</code> → <code>gate</code> passes → a new prompt regresses, the gate fails (exit 1)
          → fixed → a judged run in the center → ten labels → Calibrate → Promote.
        </figcaption>
      </figure>
      <ul className="mt-12 grid gap-8 lg:grid-cols-3">
        {SHOTS.map((s) => (
          <li key={s.src}>
            <a href={s.src} className="block" target="_blank" rel="noreferrer">
              <Image
                src={s.src}
                alt={s.alt}
                width={1440}
                height={900}
                sizes="(min-width: 1024px) 33vw, 100vw"
                className="w-full rounded-lg border border-fd-border"
              />
            </a>
            <h3 className="mt-4 font-semibold">{s.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-fd-muted-foreground">{s.body}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}
