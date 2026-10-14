import { type Page, expect } from "@playwright/test";

/** /o/[oid]/providers */
export class ProvidersPage {
  constructor(private page: Page) {}

  async goto(orgId: string) {
    await this.page.goto(`/o/${orgId}/providers`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Providers" })).toBeVisible();
  }

  row(name: string) {
    return this.page.getByTestId(`provider-${name}`);
  }

  async addProvider(name: string, apiKey: string, baseUrl = "") {
    await this.page.getByRole("button", { name: "New provider" }).click();
    const dialog = this.page.getByRole("dialog");
    await dialog.getByLabel("Name").fill(name);
    await dialog.getByLabel("API key").fill(apiKey);
    if (baseUrl) await dialog.getByLabel("Base URL (optional)").fill(baseUrl);
    await dialog.getByRole("button", { name: "Add provider" }).click();
    await expect(this.row(name)).toBeVisible();
  }

  async test(name: string, model: string) {
    await this.row(name).getByLabel(`Model to test on ${name}`).fill(model);
    await this.row(name).getByRole("button", { name: "Test" }).click();
    await expect(this.row(name).getByTestId("test-result")).toBeVisible();
  }

  async removeKey(name: string) {
    await this.row(name).getByRole("button", { name: "Edit" }).click();
    const dialog = this.page.getByRole("dialog");
    await dialog.getByLabel("Remove the stored key").check();
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();
  }

  async deleteProvider(name: string) {
    await this.row(name).getByRole("button", { name: "Delete" }).click();
    await this.page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  }
}
