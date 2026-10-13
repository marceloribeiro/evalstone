import { type Page, expect } from "@playwright/test";

/** The organization home (/o/[oid]) — the project list, and the project overview below it. */
export class ProjectsPage {
  constructor(private page: Page) {}

  async expectOrganization(name: string) {
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
  }

  async createProject(name: string) {
    await this.page.getByRole("button", { name: "New project" }).click();
    await this.page.getByLabel("Name").fill(name);
    await this.page.getByRole("button", { name: "Create" }).click();
  }

  async expectProjectOverview(name: string) {
    await expect(this.page.getByRole("heading", { level: 1, name })).toBeVisible();
    await expect(this.page.getByTestId("attach-snippet")).toContainText("center:");
  }

  async expectLive() {
    await expect(this.page.getByTestId("live-status")).toHaveText("Live");
  }

  async createIngestKey(name: string) {
    await this.page.getByLabel("Ingest key name").fill(name);
    await this.page.getByRole("button", { name: "Create ingest key" }).click();
    await expect(this.page.getByTestId("minted-key")).toContainText("EVALSTONE_API_KEY=es_");
    const text = await this.page.getByTestId("minted-key").innerText();
    return text.replace("EVALSTONE_API_KEY=", "").trim();
  }

  liveFeed() {
    return this.page.getByTestId("live-feed");
  }

  sidebar() {
    return this.page.getByTestId("sidebar");
  }

  async switchProject(name: string) {
    await this.page.getByRole("combobox", { name: "Project" }).click();
    await this.page.getByRole("option", { name }).click();
  }
}
