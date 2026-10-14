import { type Page, expect } from "@playwright/test";

/** /o/[oid]/p/[pid]/settings */
export class SettingsPage {
  constructor(private page: Page) {}

  async goto(orgId: string, projectId: string) {
    await this.page.goto(`/o/${orgId}/p/${projectId}/settings`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
  }

  async rename(name: string) {
    await this.page.getByLabel("Name", { exact: true }).fill(name);
    await this.page.getByRole("button", { name: "Save" }).click();
    await expect(this.page.getByRole("combobox", { name: "Project" })).toContainText(name); // the sidebar switcher re-read the project
  }

  async mintKey(name: string) {
    await this.page.getByLabel("New key name").fill(name);
    await this.page.getByRole("button", { name: "Create ingest key" }).click();
    await expect(this.page.getByTestId("minted-key")).toContainText("EVALSTONE_API_KEY=es_");
    await expect(this.key(name)).toContainText("active");
  }

  key(name: string) {
    return this.page.getByTestId(`key-${name}`);
  }

  async revokeKey(name: string) {
    await this.key(name).getByRole("button", { name: "Revoke" }).click();
    await expect(this.key(name)).toContainText("revoked");
  }

  async deleteProject() {
    await this.page.getByRole("button", { name: "Delete project" }).first().click();
    await this.page.getByRole("dialog").getByRole("button", { name: "Delete project" }).click();
  }
}
