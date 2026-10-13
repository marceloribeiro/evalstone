import { type Page, expect } from "@playwright/test";

/** /o/[oid]/p/[pid]/runs and the run detail under it. */
export class RunsPage {
  constructor(private page: Page) {}

  async goto(orgId: string, projectId: string) {
    await this.page.goto(`/o/${orgId}/p/${projectId}/runs`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Runs" })).toBeVisible();
  }

  table() {
    return this.page.getByRole("table", { name: "Runs" });
  }

  async filterSuite(name: string) {
    await this.page.getByRole("combobox", { name: "Suite" }).click();
    await this.page.getByRole("option", { name }).click();
  }

  async openRun(clientRunId: string) {
    await this.table().getByRole("link", { name: clientRunId }).click();
    await expect(this.page.getByRole("heading", { level: 1, name: clientRunId })).toBeVisible();
  }

  checkRow(key: string) {
    return this.page.getByTestId(`check-${key}`);
  }

  async setBaseline() {
    await this.page.getByRole("button", { name: "Set as baseline" }).click();
    await expect(this.page.getByRole("button", { name: "Unset baseline" })).toBeVisible();
  }

  async filterCheck(name: string) {
    await this.page.getByRole("combobox", { name: "Check" }).click();
    await this.page.getByRole("option", { name }).click();
  }

  async toggleFailedOnly() {
    await this.page.getByRole("button", { name: "Failed only" }).click();
  }

  resultsCount() {
    return this.page.getByTestId("results-count");
  }

  results() {
    return this.page.getByRole("table", { name: "Results" });
  }

  async expandFirstResult() {
    await this.results().getByRole("row").nth(1).click();
    await expect(this.page.getByTestId("result-detail")).toBeVisible();
  }

  async openCompare() {
    await this.page.getByRole("tab", { name: "Compare" }).click();
  }

  comparison() {
    return this.page.getByTestId("comparison");
  }
}
