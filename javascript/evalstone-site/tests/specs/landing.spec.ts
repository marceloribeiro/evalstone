import { expect, test } from '@playwright/test';
import { HomePage } from '../pages/home.page';

test.describe('Landing page', () => {
  test('presents the pitch and the two entry points', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    await expect(home.heading).toContainText('Know your LLM feature works');
    await expect(home.learnCta).toBeVisible();
    await expect(home.howItHelpsCta).toBeVisible();
    await expect(home.githubLink).toHaveAttribute('href', 'https://github.com/marceloribeiro/evalstone');
  });

  test('renders every section without JS-gated content', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    for (const id of ['problem', 'what-are-evals', 'how-it-helps', 'how-it-works', 'model-or-not', 'learn']) {
      await expect(home.section(id)).toBeVisible();
    }
    await expect(page.getByRole('heading', { name: 'Evals 101, nine short chapters' })).toBeVisible();
  });

  test('puts the judge first and says what runs without a model', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    const section = home.section('model-or-not');
    const headings = await section.getByRole('heading', { level: 3 }).allTextContents();
    expect(headings).toEqual([
      'LLM-as-judge, with your model',
      'Human labels',
      'Deterministic checks, no model needed',
    ]);
    await expect(section.getByText('openrouter.ai')).toBeVisible();
    await section.getByRole('link', { name: /How Evalstone works, in full/ }).click();
    await expect(page).toHaveURL(/\/docs\/evalstone\/how-it-works$/);
  });

  test('the top nav reaches every section of the docs', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();
    for (const [name, path, heading] of [
      ['Learn evals', '/docs/learn', 'Evals 101'],
      ['How it works', '/docs/evalstone/how-it-works', 'How it works'],
      ['Evalstone', '/docs/evalstone', 'How Evalstone helps'],
      ['Guides', '/docs/guides/quickstart', 'Quickstart'],
      ['Reference', '/docs/reference/cli', 'CLI'],
    ] as const) {
      await home.goto();
      const link = page.locator(`header a[href="${path}"]:visible`).first();
      await expect(link).toHaveText(name);
      await link.click();
      await expect(page).toHaveURL(new RegExp(`${path.replace(/\//g, '\\/')}$`));
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading);
    }
  });

  test('the learning CTA opens Evals 101', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();
    await home.learnCta.click();

    await expect(page).toHaveURL(/\/docs\/learn$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Evals 101');
  });
});
