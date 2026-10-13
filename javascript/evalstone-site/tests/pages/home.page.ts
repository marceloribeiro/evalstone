import type { Locator, Page } from '@playwright/test';

export class HomePage {
  readonly heading: Locator;
  readonly learnCta: Locator;
  readonly howItHelpsCta: Locator;
  readonly githubLink: Locator;

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { level: 1 });
    this.learnCta = page.getByRole('link', { name: 'Start with Evals 101' });
    this.howItHelpsCta = page.getByRole('link', { name: 'How Evalstone helps' });
    this.githubLink = page.locator('section').first().getByRole('link', { name: 'GitHub', exact: true });
  }

  async goto() {
    await this.page.goto('/');
  }

  section(id: string) {
    return this.page.locator(`section#${id}`);
  }
}
