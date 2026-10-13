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

  test('says what needs a model and what does not', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    const section = home.section('model-or-not');
    await expect(section.getByRole('heading', { name: 'No model needed' })).toBeVisible();
    await expect(section.getByRole('heading', { name: 'Needs a model, yours' })).toBeVisible();
    await expect(section.getByText('openrouter.ai')).toBeVisible();
    await section.getByRole('link', { name: /How Evalstone works, in full/ }).click();
    await expect(page).toHaveURL(/\/docs\/evalstone\/how-it-works$/);
  });

  test('the learning CTA opens Evals 101', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();
    await home.learnCta.click();

    await expect(page).toHaveURL(/\/docs\/learn$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Evals 101');
  });
});
