import { Hero } from '@/components/landing/hero';
import { Problem } from '@/components/landing/problem';
import { WhatAreEvals } from '@/components/landing/what-are-evals';
import { HowItHelps } from '@/components/landing/how-it-helps';
import { HowItWorks } from '@/components/landing/how-it-works';
import { LearnCards } from '@/components/landing/learn-cards';
import { StatusAndCta } from '@/components/landing/status-and-cta';
import { Footer } from '@/components/landing/footer';

export default function HomePage() {
  return (
    <main className="flex-1">
      <Hero />
      <Problem />
      <WhatAreEvals />
      <HowItHelps />
      <HowItWorks />
      <LearnCards />
      <StatusAndCta />
      <Footer />
    </main>
  );
}
