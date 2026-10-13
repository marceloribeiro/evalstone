import type { Locator, Page } from '@playwright/test';

export class DocsPage {
  readonly title: Locator;

  constructor(private readonly page: Page) {
    this.title = page.getByRole('heading', { level: 1 });
  }

  async goto(path: string) {
    await this.page.goto(`/docs${path}`);
  }

  sidebarLink(name: string) {
    return this.page.getByRole('link', { name, exact: true }).first();
  }
}
