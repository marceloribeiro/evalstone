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
    await docs.goto('/evalstone');
    await expect(page.getByText('Status', { exact: true })).toBeVisible();
    await docs.goto('/evalstone/how-it-works');
    await expect(page.getByText('Released', { exact: true })).toBeVisible();
    await docs.goto('/evalstone/library');
    await expect(page.getByText('Released', { exact: true })).toBeVisible();
    await docs.goto('/evalstone/center');
    await expect(page.getByText('Planned', { exact: true })).toBeVisible();
  });

  test('the markdown mirror serves a chapter as text', async ({ request }) => {
    const res = await request.get('/llms.mdx/docs/learn/pitfalls/content.md');
    expect(res.ok()).toBeTruthy();
    expect(await res.text()).toContain('Overfitting the golden set');
  });
});

const GUIDES_AND_REFERENCE: Array<[string, string]> = [
  ['/evalstone/how-it-works', 'How it works'],
  ['/guides/quickstart', 'Quickstart'],
  ['/guides/ci', 'Evals in CI'],
  ['/guides/mcp', 'Evals from your coding agent'],
  ['/guides/labeling', 'Labeling outputs'],
  ['/reference/cli', 'CLI'],
  ['/reference/config', 'evalstone.yaml'],
  ['/reference/checks', 'Checks catalog'],
];

test.describe('Guides and reference', () => {
  for (const [path, title] of GUIDES_AND_REFERENCE) {
    test(`page "${title}" renders`, async ({ page }) => {
      const docs = new DocsPage(page);
      await docs.goto(path);
      await expect(docs.title).toHaveText(title);
    });
  }

  // completeness against the library's FACTORIES is asserted by python/evalstone/tests/test_docs.py
  test('the checks catalog renders rows from every check family', async ({ page }) => {
    const docs = new DocsPage(page);
    await docs.goto('/reference/checks');
    for (const type of ['json_schema', 'judge', 'rag.faithfulness', 'safety.no_pii', 'comparison.pairwise', 'trajectory.tool_called', 'human']) {
      await expect(page.getByText(type, { exact: true }).first()).toBeVisible();
    }
  });

  test('the docs home links the new sections', async ({ page }) => {
    const docs = new DocsPage(page);
    await docs.goto('');
    await page.getByRole('link', { name: /^Guides/ }).first().click();
    await expect(page).toHaveURL(/\/docs\/guides\/quickstart$/);
  });
});
