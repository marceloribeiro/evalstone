import { type Page, expect } from "@playwright/test";

export class OrganizationsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/organizations");
    await expect(this.page.getByRole("heading", { name: "Organizations" })).toBeVisible();
  }

  async createOrganization(name: string) {
    await this.page.getByRole("button", { name: "New organization" }).click();
    await this.page.getByLabel("Name").fill(name);
    await this.page.getByRole("button", { name: "Create" }).click();
  }

  async expectOrganization(name: string) {
    await expect(this.page.getByRole("list", { name: "Organizations" }).getByText(name)).toBeVisible();
  }

  async open(name: string) {
    await this.page.getByRole("list", { name: "Organizations" }).getByRole("link", { name }).click();
  }

  async signOut() {
    await this.page.getByRole("button", { name: "Sign out" }).click();
  }
}
