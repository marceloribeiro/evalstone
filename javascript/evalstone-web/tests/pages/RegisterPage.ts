import { type Page, expect } from "@playwright/test";

export class RegisterPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/register");
    await expect(this.page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  }

  async register(email: string, password: string, firstName = "Play", lastName = "Wright") {
    await this.page.getByLabel("First name").fill(firstName);
    await this.page.getByLabel("Last name").fill(lastName);
    await this.page.getByLabel("Email").fill(email);
    await this.page.getByLabel("Password").fill(password);
    await this.page.getByRole("button", { name: "Create account" }).click();
  }
}
