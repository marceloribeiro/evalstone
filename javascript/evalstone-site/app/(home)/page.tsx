import { Hero } from '@/components/landing/hero';
import { SeeIt } from '@/components/landing/see-it';
import { Problem } from '@/components/landing/problem';
import { WhatAreEvals } from '@/components/landing/what-are-evals';
import { HowItHelps } from '@/components/landing/how-it-helps';
import { HowItWorks } from '@/components/landing/how-it-works';
import { ModelOrNot } from '@/components/landing/model-or-not';
import { LearnCards } from '@/components/landing/learn-cards';
import { StatusAndCta } from '@/components/landing/status-and-cta';
import { Footer } from '@/components/landing/footer';

export default function HomePage() {
  return (
    <main className="flex-1">
      <Hero />
      <SeeIt />
      <Problem />
      <WhatAreEvals />
      <HowItHelps />
      <HowItWorks />
      <ModelOrNot />
      <LearnCards />
      <StatusAndCta />
      <Footer />
    </main>
  );
}
