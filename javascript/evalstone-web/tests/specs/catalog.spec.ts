import { test, expect } from "../fixtures/auth";
import { authed, inviteMember, newOrganization, newProject, newUser } from "../fixtures/api";
import { CatalogPage } from "../pages/CatalogPage";
import { LoginPage } from "../pages/LoginPage";

test.describe("Check catalog", () => {
  test("an admin creates a check from a built-in type, versions it with a note, sees the YAML block, and deletes it", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Catalog Org");
    const catalog = new CatalogPage(page);
    await catalog.goto(org.id);
    await expect(page.getByText("No checks yet")).toBeVisible();
    await catalog.createCheck("has-paris", "contains", { needles: "Paris, France" }, "The answer names the city");
    await expect(catalog.params()).toContainText("type: contains");
    await expect(catalog.params()).toContainText("- Paris");
    await expect(catalog.params()).toContainText("- France");
    await expect(page.getByTestId("check-description")).toContainText("names the city");
    await expect(catalog.versions().getByTestId("version-1")).toContainText("current");

    // a params change with a note → v2; a description-only edit stays on v2
    await catalog.edit({ needles: "Paris" }, { note: "France was too lenient" });
    await expect(catalog.versions().getByTestId("version-2")).toContainText("France was too lenient");
    await expect(catalog.versions().getByTestId("version-2")).toContainText("current");
    await expect(catalog.params()).not.toContainText("- France");
    await catalog.edit({}, { description: "City check" });
    await expect(page.getByTestId("check-description")).toContainText("City check");
    await expect(catalog.versions().getByTestId("version-3")).toHaveCount(0);
    // a note without a content change is refused by the API (shown as a toast, the dialog stays open)
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByRole("dialog").getByLabel(/Version note/).fill("why");
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await expect(page.locator("[data-sonner-toast]").filter({ hasText: "nothing changed" }).first()).toBeVisible();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();

    await catalog.goto(org.id);
    await expect(catalog.row("has-paris")).toContainText("v2");
    await expect(catalog.yaml()).toContainText("checks:");
    await expect(catalog.yaml()).toContainText("has-paris:");
    await expect(catalog.yaml()).toContainText("type: contains");
    const block = (await authed(seed, "get", `/organizations/${org.id}/checks/yaml`)) as { checks: Record<string, unknown> };
    expect(block.checks["has-paris"]).toEqual({ type: "contains", needles: ["Paris"] });

    // the monitor form offers the check (the catalog is the only source of monitor checks)
    const project = await newProject(seed, org.id, "Catalog Project");
    await page.goto(`/o/${org.id}/p/${project.id}/monitors`);
    await page.getByRole("button", { name: "New monitor" }).click();
    await expect(page.getByRole("dialog").getByRole("checkbox", { name: /^has-paris / })).toBeVisible();
    await page.keyboard.press("Escape");

    await catalog.goto(org.id);
    await catalog.openCheck("has-paris");
    await catalog.deleteCheck();
    await expect(page.getByText("No checks yet")).toBeVisible();
  });

  test("the form refuses a bad key and a missing required param before sending; a member sees the catalog read-only", async ({ page, seed }) => {
    const org = await newOrganization(seed, "RO Catalog Org");
    await authed(seed, "post", `/organizations/${org.id}/checks`, { key: "short", type: "length", params: { max_chars: 200 } });
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(seed.email, seed.password);
    await page.waitForURL(/\/(organizations|o\/)/);
    const catalog = new CatalogPage(page);
    await catalog.goto(org.id);
    await page.getByRole("button", { name: "New check" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Key").fill("Has Paris");
    await expect(dialog.getByRole("alert")).toContainText("lowercase");
    await dialog.getByLabel("Key").fill("has-paris");
    await dialog.getByRole("combobox", { name: "Check type" }).click();
    await page.getByRole("option", { name: /^contains —/ }).click();
    await expect(dialog.getByRole("button", { name: "Create" })).toBeDisabled(); // needles is required
    await expect(dialog.getByRole("alert").filter({ hasText: "required" })).toBeVisible();
    await page.keyboard.press("Escape");

    const member = await newUser("viewer");
    await inviteMember(seed, org.id, member.email);
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL(/\/login$/);
    await login.signIn(member.email, member.password);
    await page.waitForURL(/\/(organizations|o\/)/);
    await catalog.goto(org.id);
    await expect(catalog.row("short")).toContainText("length");
    await expect(page.getByRole("button", { name: "New check" })).toHaveCount(0);
    await catalog.openCheck("short");
    await expect(catalog.params()).toContainText("max_chars: 200");
    await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Delete", exact: true })).toHaveCount(0);
    await member.api.dispose();
  });
});
