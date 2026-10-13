import { expect, test } from '@playwright/test';
import { DocsPage } from '../pages/docs.page';

const CHAPTERS: Array<[string, string]> = [
  ['/learn/what-are-evals', 'What are evals?'],
  ['/learn/why-you-need-them', 'Why you need them'],
  ['/learn/the-eval-loop', 'The eval loop'],
  ['/learn/kinds-of-checks', 'Kinds of checks'],
  ['/learn/building-a-golden-set', 'Building a golden set'],
  ['/learn/llm-as-judge', 'LLM-as-judge done right'],
  ['/learn/gates-and-ci', 'Gates and CI'],
  ['/learn/evals-in-production', 'Evals in production'],
  ['/learn/pitfalls', 'Pitfalls'],
];

test.describe('Learning center', () => {
  test('the docs home links both halves', async ({ page }) => {
    const docs = new DocsPage(page);
    await docs.goto('');
    await expect(docs.title).toHaveText('Welcome');
    await expect(page.getByRole('link', { name: /Learn evals/ }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /^Evalstone/ }).first()).toBeVisible();
  });

  for (const [path, title] of CHAPTERS) {
    test(`chapter "${title}" renders`, async ({ page }) => {
      const docs = new DocsPage(page);
      await docs.goto(path);
      await expect(docs.title).toHaveText(title);
    });
  }

  test('chapters chain with a "Next" link', async ({ page }) => {
    const docs = new DocsPage(page);
    await docs.goto('/learn/what-are-evals');
    await page.getByRole('link', { name: 'Why you need them' }).first().click();
    await expect(page).toHaveURL(/\/docs\/learn\/why-you-need-them$/);
  });

  test('Evalstone pages state their status honestly', async ({ page }) => {
    const docs = new DocsPage(page);
    await docs.goto('/evalstone/library');
    await expect(page.getByText('Not yet released')).toBeVisible();
    await docs.goto('/evalstone/center');
    await expect(page.getByText('Planned', { exact: true })).toBeVisible();
  });

  test('the markdown mirror serves a chapter as text', async ({ request }) => {
    const res = await request.get('/llms.mdx/docs/learn/pitfalls/content.md');
    expect(res.ok()).toBeTruthy();
    expect(await res.text()).toContain('Overfitting the golden set');
  });
});
