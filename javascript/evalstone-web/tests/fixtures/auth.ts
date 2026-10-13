import { test as base, expect, type Page } from "@playwright/test";
import { newUser, type Seed } from "./api";
import { LoginPage } from "../pages/LoginPage";

type Fixtures = { seed: Seed; authedPage: Page };

/** A fresh user per test, signed in through the real login form. */
export const test = base.extend<Fixtures>({
  seed: async ({}, provide) => {
    const seed = await newUser();
    await provide(seed);
    await seed.api.dispose();
  },
  authedPage: async ({ page, seed }, provide) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(seed.email, seed.password);
    await page.waitForURL(/\/organizations$/);
    await provide(page);
  },
});

export { expect };
