import { type Page, expect } from "@playwright/test";

/** /o/[oid]/p/[pid]/datasets and the dataset detail under it. */
export class DatasetsPage {
  constructor(private page: Page) {}

  async goto(orgId: string, projectId: string) {
    await this.page.goto(`/o/${orgId}/p/${projectId}/datasets`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Datasets" })).toBeVisible();
  }

  table() {
    return this.page.getByRole("table", { name: "Datasets" });
  }

  async createDataset(name: string, description = "", tags = "") {
    await this.page.getByRole("button", { name: "New dataset" }).click();
    await this.page.getByLabel("Name").fill(name);
    if (description) await this.page.getByLabel("Description").fill(description);
    if (tags) await this.page.getByLabel("Tags (comma-separated)").fill(tags);
    await this.page.getByRole("button", { name: "Create" }).click();
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
    return this.page.url().split("/datasets/")[1]; // the id the app navigated to
  }

  addTagInput() {
    return this.page.getByLabel("Add tag");
  }

  async openDataset(name: string) {
    await this.table().getByRole("link", { name }).click();
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
  }

  tags() {
    return this.page.getByTestId("tags").getByRole("list", { name: "Tags" });
  }

  async addTag(tag: string) {
    await this.page.getByLabel("Add tag").fill(tag);
    await this.page.getByLabel("Add tag").press("Enter");
    await expect(this.tags()).toContainText(tag);
  }

  async removeTag(tag: string) {
    await this.page.getByRole("button", { name: `Remove tag ${tag}` }).click();
    await expect(this.tags()).not.toContainText(tag);
  }

  versions() {
    return this.page.getByRole("table", { name: "Versions" });
  }

  async chooseVersion(n: number) {
    await this.versions().getByRole("button", { name: `v${n}`, exact: true }).click();
    await expect(this.page.getByRole("tab", { name: `Samples of v${n}` })).toBeVisible();
  }

  async openSamples(n: number) {
    await this.page.getByRole("tab", { name: `Samples of v${n}` }).click();
  }

  samples() {
    return this.page.getByRole("table", { name: "Samples" });
  }

  async openDiff() {
    await this.page.getByRole("tab", { name: "Diff" }).click();
  }

  diff() {
    return this.page.getByTestId("diff");
  }

  async diffAgainst(n: number) {
    await this.page.getByRole("combobox", { name: "Diff against" }).click();
    await this.page.getByRole("option", { name: new RegExp(`^v${n} ·`) }).click();
  }

  async deleteDataset() {
    await this.page.getByRole("button", { name: "Delete dataset" }).click();
    await this.page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(this.page.getByRole("heading", { level: 1, name: "Datasets" })).toBeVisible();
  }
}
