import { type Page, expect } from "@playwright/test";

/** /o/[oid]/p/[pid]/labeling, a queue's detail, and the labeler under it. */
export class LabelingPage {
  constructor(private page: Page) {}

  async goto(orgId: string, projectId: string) {
    await this.page.goto(`/o/${orgId}/p/${projectId}/labeling`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Labeling" })).toBeVisible();
  }

  queues() {
    return this.page.getByRole("table", { name: "Queues" });
  }

  async openQueue(name: string) {
    await this.queues().getByRole("link", { name }).click();
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
  }

  async newGradeQueue(name: string, run: string, opts: { check?: string; failedOnly?: boolean; scale?: string; instructions?: string } = {}) {
    await this.page.getByRole("button", { name: "New queue" }).click();
    await this.page.getByLabel("Name").fill(name);
    await this.page.getByRole("combobox", { name: "Run" }).click();
    await this.page.getByRole("option", { name: new RegExp(`^${run} ·`) }).click();
    if (opts.check) {
      await this.page.getByRole("combobox", { name: "Source check" }).click();
      await this.page.getByRole("option", { name: opts.check, exact: true }).click();
    }
    if (opts.failedOnly) await this.page.getByLabel("Failed results only").check();
    if (opts.scale) await this.page.getByLabel("Scale (2 = pass/fail)").fill(opts.scale);
    if (opts.instructions) await this.page.getByLabel("Instructions for labelers").fill(opts.instructions);
    await this.page.getByRole("button", { name: "Create" }).click();
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
    return this.page.url().split("/labeling/")[1];
  }

  progress() {
    return this.page.locator('dl[aria-label="Progress"]');
  }

  async gotoQueue(orgId: string, projectId: string, queueId: string, name: string) {
    await this.page.goto(`/o/${orgId}/p/${projectId}/labeling/${queueId}`);
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
  }

  async startLabeling() {
    await this.page.getByRole("link", { name: "Label", exact: true }).click();
    await expect(this.page.getByTestId("task").or(this.page.getByTestId("queue-done"))).toBeVisible();
  }

  task() {
    return this.page.getByTestId("task");
  }

  counter() {
    return this.page.getByTestId("counter");
  }

  /** The task on screen (fails with "no task on screen" rather than hanging when there is none). */
  async currentTaskId() {
    await expect(this.task(), "no task on screen").toBeVisible();
    return this.task().getAttribute("data-task-id");
  }

  /** Press keys and wait until a different task (or the end card) is on screen. */
  async verdict(keys: string[]) {
    const before = await this.currentTaskId();
    // the panel marks itself hotkey-ready from the effect that attaches the keydown listener, and
    // nothing interactive may hold focus (a focused button would take Enter as its own click)
    await expect(this.page.locator('[data-testid="verdict"][data-hotkeys="ready"]'), "verdict panel hotkeys not ready").toBeVisible();
    await expect
      .poll(() => this.page.evaluate(() => { const a = document.activeElement; return !a || a === document.body || !a.matches("button, a, input, select, textarea, [contenteditable]"); }), { message: "something interactive holds focus" })
      .toBe(true);
    for (const k of keys) await this.page.keyboard.press(k);
    // one self-retrying, strict assertion: the done card, a task other than `before`, or an error
    // surfaced by the app (reported instead of waiting out the clock)
    const outcome = this.page.locator(`[data-testid="queue-done"], [data-testid="task"]:not([data-task-id="${before}"]), [data-testid="load-error"], [data-sonner-toast][data-type="error"]`);
    await expect(outcome.first(), `verdict ${keys.join("+")} → next task or done card`).toBeVisible({ timeout: 10_000 });
    const kind = await outcome.first().evaluate((el) => el.getAttribute("data-testid") ?? "toast");
    if (kind === "load-error" || kind === "toast") throw new Error(`verdict ${keys.join("+")} failed: ${await outcome.first().innerText()}`);
    await expect(this.task(), "more than one task on screen").toHaveCount(await this.page.getByTestId("queue-done").count() ? 0 : 1);
  }

  async expectDone() {
    await expect(this.page.getByTestId("queue-done")).toBeVisible();
  }

  tasks() {
    return this.page.getByRole("table", { name: "Tasks" });
  }
}
