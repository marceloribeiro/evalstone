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

    for (const id of ['see-it', 'problem', 'what-are-evals', 'how-it-helps', 'how-it-works', 'model-or-not', 'learn']) {
      await expect(home.section(id)).toBeVisible();
    }
    await expect(page.getByRole('heading', { name: 'Evals 101, nine short chapters' })).toBeVisible();
  });

  test('shows the walkthrough video and the three center screenshots, all loaded', async ({ page, request }) => {
    const home = new HomePage(page);
    await home.goto();

    const section = home.section('see-it');
    await expect(section.getByRole('heading', { name: 'One minute, end to end' })).toBeVisible();
    const video = section.locator('video');
    await expect(video).toHaveAttribute('src', '/media/walkthrough.mp4');
    expect((await request.get('/media/walkthrough.mp4')).status()).toBe(200);
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(1);

    const images = section.getByRole('img');
    await expect(images).toHaveCount(3);
    for (const img of await images.all()) {
      await img.scrollIntoViewIfNeeded();
      await expect.poll(() => img.evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth)).toBeGreaterThan(0);
    }
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

  test('the top nav walks the sections of this page, and reaches the docs', async ({ page }) => {
    const home = new HomePage(page);
    for (const [name, id] of [
      ['Problem', 'problem'],
      ['Evals', 'what-are-evals'],
      ['How it helps', 'how-it-helps'],
      ['How it works', 'how-it-works'],
      ['Model', 'model-or-not'],
      ['Learn', 'learn'],
    ] as const) {
      await home.goto();
      const link = page.locator(`header a[href="/#${id}"]:visible`).first();
      await expect(link).toHaveText(name);
      await link.click();
      await expect(page).toHaveURL(new RegExp(`/#${id}$`));
      const box = await home.section(id).boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(0); // not hidden under the sticky header
      expect(box!.y).toBeLessThanOrEqual(64); // and parked right below it
    }
    await home.goto();
    await page.locator('header a[href="/docs"]:visible').first().click();
    await expect(page).toHaveURL(/\/docs$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Welcome');
  });

  test('the header fits at tablet widths without horizontal overflow', async ({ page }) => {
    // 640–672px (fumadocs shows the links and the menu trigger together there) overflows by
    // a few pixels of the trigger itself; from 700px up the header must fit.
    for (const width of [700, 768, 820, 1024]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('/');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflow, `horizontal overflow at ${width}px`).toBe(false);
      await expect(page.locator('header a[href="/#learn"]:visible').first()).toBeVisible();
      await expect(page.locator('header a[href="/docs"]:visible').first()).toBeVisible();
    }
  });

  test('a docs page reaches the homepage sections through the Home menu', async ({ page }) => {
    await page.goto('/docs/guides/quickstart');
    await page.getByRole('button', { name: 'Home' }).or(page.getByText('Home', { exact: true })).first().click();
    await page.locator('a[href="/#model-or-not"]:visible').first().click();
    await expect(page).toHaveURL(/\/#model-or-not$/);
    await expect(page.locator('#model-or-not')).toBeInViewport();
  });

  test('a phone sees every section link in the menu', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.getByRole('button', { name: /menu/i }).click();
    for (const id of ['problem', 'what-are-evals', 'how-it-helps', 'how-it-works', 'model-or-not', 'learn']) {
      await expect(page.locator(`a[href="/#${id}"]:visible`).first()).toBeVisible();
    }
    await expect(page.locator('a[href="/docs"]:visible').first()).toBeVisible();
  });

  test('the learning CTA opens Evals 101', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();
    await home.learnCta.click();

    await expect(page).toHaveURL(/\/docs\/learn$/);
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Evals 101');
  });
});
