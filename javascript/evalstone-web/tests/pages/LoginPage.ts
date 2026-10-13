import { type Page, expect } from "@playwright/test";

export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/login");
    await expect(this.page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  }

  async signIn(email: string, password: string) {
    await this.page.getByLabel("Email").fill(email);
    await this.page.getByLabel("Password").fill(password);
    await this.page.getByRole("button", { name: "Sign in" }).click();
  }

  async expectError(text: string | RegExp) {
    await expect(this.page.getByRole("main").getByRole("alert")).toContainText(text);
  }
}
