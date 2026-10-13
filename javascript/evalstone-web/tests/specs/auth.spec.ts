import { test, expect } from "../fixtures/auth";
import { newUser } from "../fixtures/api";
import { LoginPage } from "../pages/LoginPage";
import { RegisterPage } from "../pages/RegisterPage";
import { OrganizationsPage } from "../pages/OrganizationsPage";

test.describe("Authentication", () => {
  test("a visitor registers and lands on the organizations page", async ({ page }) => {
    const register = new RegisterPage(page);
    await register.goto();
    const email = `new-${Date.now()}@example.com`;
    await register.register(email, "playwright-pass-1");
    await page.waitForURL(/\/organizations$/);
    await expect(page.getByText(email)).toBeVisible();
  });

  test("a user signs in, is remembered across a reload, and signs out", async ({ page, seed }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(seed.email, seed.password);
    await page.waitForURL(/\/organizations$/);
    await page.reload();
    await expect(page.getByText(seed.email)).toBeVisible();
    await new OrganizationsPage(page).signOut();
    await page.waitForURL(/\/login$/);
    await page.goto("/organizations");
    await page.waitForURL(/\/login$/); // signed out: the guard redirects
  });

  test("a wrong password shows the API's error, not a crash", async ({ page }) => {
    const seed = await newUser();
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(seed.email, "not-the-password");
    await login.expectError("invalid email or password");
    await seed.api.dispose();
  });
});
