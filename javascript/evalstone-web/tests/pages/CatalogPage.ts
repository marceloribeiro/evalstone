import { type Page, expect } from "@playwright/test";

/** /o/[oid]/checks and a check's detail. */
export class CatalogPage {
  constructor(private page: Page) {}

  async goto(orgId: string) {
    await this.page.goto(`/o/${orgId}/checks`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Check catalog" })).toBeVisible();
  }

  row(key: string) {
    return this.page.getByTestId(`check-${key}`);
  }

  /** New check: pick the type, fill params by name, create; lands on the detail page. */
  async createCheck(key: string, type: string, params: Record<string, string>, description = "") {
    await this.page.getByRole("button", { name: "New check" }).click();
    const dialog = this.page.getByRole("dialog");
    await dialog.getByLabel("Key").fill(key);
    await dialog.getByRole("combobox", { name: "Check type" }).click();
    await this.page.getByRole("option", { name: new RegExp(`^${type.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} —`) }).click();
    for (const [name, value] of Object.entries(params)) await dialog.getByLabel(new RegExp(`^${name}\\b`)).fill(value);
    if (description) await dialog.getByLabel("Description").fill(description);
    await dialog.getByRole("button", { name: "Create" }).click();
    await expect(this.page.getByRole("heading", { level: 1, name: key })).toBeVisible();
    return this.page.url().split("/checks/")[1];
  }

  async openCheck(key: string) {
    await this.row(key).getByRole("link", { name: key }).click();
    await expect(this.page.getByRole("heading", { level: 1, name: key })).toBeVisible();
  }

  params() {
    return this.page.getByTestId("check-params");
  }

  versions() {
    return this.page.getByRole("table", { name: "Versions" });
  }

  /** Edit: change params (and/or description) with a note; saves and waits for the detail to refresh. */
  async edit(params: Record<string, string>, opts: { note?: string; description?: string } = {}) {
    await this.page.getByRole("button", { name: "Edit" }).click();
    const dialog = this.page.getByRole("dialog");
    for (const [name, value] of Object.entries(params)) await dialog.getByLabel(new RegExp(`^${name}\\b`)).fill(value);
    if (opts.description !== undefined) await dialog.getByLabel("Description").fill(opts.description);
    if (opts.note !== undefined) await dialog.getByLabel(/Version note/).fill(opts.note);
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();
  }

  yaml() {
    return this.page.getByTestId("checks-yaml");
  }

  async deleteCheck() {
    await this.page.getByRole("button", { name: "Delete", exact: true }).click();
    await this.page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(this.page.getByRole("heading", { level: 1, name: "Check catalog" })).toBeVisible();
  }
}
