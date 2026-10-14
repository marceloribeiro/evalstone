import { type Page, expect } from "@playwright/test";

/** /o/[oid]/p/[pid]/monitors, a monitor's detail, and /alerts. */
export class MonitorsPage {
  constructor(private page: Page) {}

  async goto(orgId: string, projectId: string) {
    await this.page.goto(`/o/${orgId}/p/${projectId}/monitors`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Monitors" })).toBeVisible();
  }

  async gotoAlerts(orgId: string, projectId: string) {
    await this.page.goto(`/o/${orgId}/p/${projectId}/alerts`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Alerts" })).toBeVisible();
  }

  monitors() {
    return this.page.getByRole("table", { name: "Monitors" });
  }

  async createMonitor(name: string, checks: string[], opts: { sample?: string; threshold?: string; window?: string; minN?: string } = {}) {
    await this.page.getByRole("button", { name: "New monitor" }).click();
    const dialog = this.page.getByRole("dialog");
    await dialog.getByLabel("Name").fill(name);
    for (const c of checks) await dialog.getByRole("checkbox", { name: new RegExp(`^${c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} `) }).check();
    if (opts.sample) await dialog.getByLabel("Sample rate (%)").fill(opts.sample);
    if (opts.threshold) await dialog.getByLabel(/Alert below/).fill(opts.threshold);
    if (opts.window) await dialog.getByLabel("Window (minutes)").fill(opts.window);
    if (opts.minN) await dialog.getByLabel("Minimum traces to alert").fill(opts.minN);
    await dialog.getByRole("button", { name: "Create" }).click();
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
    return this.page.url().split("/monitors/")[1];
  }

  async openMonitor(name: string) {
    await this.monitors().getByRole("link", { name }).click();
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
  }

  window() {
    return this.page.locator('dl[aria-label="Window"]');
  }

  /** The value of one window tile by its label. */
  tile(label: RegExp | string) {
    return this.window().locator("div").filter({ has: this.page.locator("dt", { hasText: label }) }).locator("dd");
  }

  status() {
    return this.page.getByTestId("monitor-status");
  }

  async scoreNow() {
    await this.page.getByRole("button", { name: "Score now" }).click();
  }

  alerts() {
    return this.page.getByRole("table", { name: "Alerts" });
  }

  alertRows(state: "open" | "resolved") {
    return this.alerts().locator(`tr[data-state="${state}"]`);
  }

  traces() {
    return this.page.getByRole("table", { name: "Traces" });
  }

  /** Flag the first trace on the page (newest); returns its client id. */
  async flagFirst() {
    const button = this.traces().getByRole("button", { name: /^Flag trace / }).first();
    const id = (await button.getAttribute("aria-label"))!.replace("Flag trace ", "");
    await button.click();
    await expect(this.page.getByRole("button", { name: `Unflag trace ${id}` })).toBeVisible();
    return id;
  }

  async pause() {
    await this.page.getByRole("button", { name: "Pause" }).click();
    await expect(this.status()).toHaveText("paused");
  }

  async deleteMonitor() {
    await this.page.getByRole("button", { name: "Delete", exact: true }).click();
    await this.page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(this.page.getByRole("heading", { level: 1, name: "Monitors" })).toBeVisible();
  }
}
