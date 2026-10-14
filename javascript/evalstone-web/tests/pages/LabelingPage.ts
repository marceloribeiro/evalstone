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

  async currentTaskId() {
    return this.task().getAttribute("data-task-id");
  }

  /** Press keys and wait until a different task (or the end card) is on screen. */
  async verdict(keys: string[]) {
    // hotkeys are live once nothing interactive holds focus (the task container takes it on arrival;
    // Escape from the notes box leaves it on the body)
    await expect
      .poll(() => this.page.evaluate(() => { const a = document.activeElement; return !a || a === document.body || !a.matches("button, a, input, select, textarea, [contenteditable]"); }))
      .toBe(true);
    const before = await this.currentTaskId();
    for (const k of keys) await this.page.keyboard.press(k);
    await expect
      .poll(async () => (await this.page.getByTestId("queue-done").count()) > 0 || (await this.task().getAttribute("data-task-id")) !== before)
      .toBe(true);
  }

  async expectDone() {
    await expect(this.page.getByTestId("queue-done")).toBeVisible();
  }

  tasks() {
    return this.page.getByRole("table", { name: "Tasks" });
  }
}
