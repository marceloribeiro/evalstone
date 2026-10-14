import { type Page, expect } from "@playwright/test";

/** /o/[oid]/p/[pid]/judges */
export class JudgesPage {
  constructor(private page: Page) {}

  async goto(orgId: string, projectId: string) {
    await this.page.goto(`/o/${orgId}/p/${projectId}/judges`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Judges" })).toBeVisible();
  }

  settings() {
    return this.page.getByTestId("judge-settings");
  }

  async setDefaultModel(model: string) {
    await this.page.getByRole("button", { name: "Edit judge settings" }).click();
    await this.page.getByLabel("Default model").fill(model);
    await this.page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(this.settings()).toContainText(model);
  }

  async addOverride(check: string, model: string) {
    await this.page.getByRole("button", { name: "Edit judge settings" }).click();
    await this.page.getByRole("button", { name: "Add override" }).click();
    const n = await this.page.getByLabel(/Override \d+ check/).count();
    await this.page.getByLabel(`Override ${n} check`).fill(check);
    await this.page.getByLabel(`Override ${n} model`).fill(model);
    await this.page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(this.settings().getByRole("list", { name: "Overrides" })).toContainText(`${check} → ${model}`);
  }

  judges() {
    return this.page.getByRole("table", { name: "Judges seen" });
  }

  calibrations() {
    return this.page.getByRole("table", { name: "Calibrations" });
  }

  async calibrate(check: string, labelCheck?: string) {
    await this.judges().getByRole("row").filter({ hasText: check }).getByRole("button", { name: "Calibrate" }).click();
    const dialog = this.page.getByRole("dialog");
    if (labelCheck !== undefined) await dialog.getByLabel(/Labels under check/).fill(labelCheck);
    await dialog.getByRole("button", { name: "Run calibration" }).click();
    await expect(dialog).toBeHidden();
  }

  calibrationRow(check: string) {
    return this.calibrations().getByRole("row").filter({ hasText: check }).first();
  }

  async promote(check: string) {
    await this.calibrationRow(check).getByRole("button", { name: "Promote" }).click();
    await expect(this.calibrationRow(check).getByRole("button", { name: "Promoted" })).toBeVisible();
  }
}
