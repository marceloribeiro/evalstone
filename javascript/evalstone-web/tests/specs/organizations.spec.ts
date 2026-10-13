import { test, expect } from "../fixtures/auth";
import { newOrganization } from "../fixtures/api";
import { OrganizationsPage } from "../pages/OrganizationsPage";
import { ProjectsPage } from "../pages/ProjectsPage";

test.describe("Organizations and projects", () => {
  test("a new user creates an organization and a project and lands on the project home", async ({ authedPage: page }) => {
    const orgs = new OrganizationsPage(page);
    await expect(page.getByText("You are not in an organization yet")).toBeVisible();
    await orgs.createOrganization("Acme Evals");
    await page.waitForURL(/\/o\/[0-9a-f-]+$/);
    const projects = new ProjectsPage(page);
    await projects.expectOrganization("Acme Evals");
    await expect(page.getByText("No projects yet")).toBeVisible();
    await projects.createProject("Support Bot");
    await page.waitForURL(/\/o\/[0-9a-f-]+\/p\/[0-9a-f-]+$/);
    await projects.expectProjectOverview("Support Bot");
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Acme Evals");
  });

  test("an existing organization is listed and opens; the sidebar switcher moves between projects", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Listed Org");
    const projects = new ProjectsPage(page);
    const orgs = new OrganizationsPage(page);
    await orgs.goto();
    await orgs.expectOrganization("Listed Org");
    await orgs.open("Listed Org");
    await page.waitForURL(`**/o/${org.id}`);
    await projects.createProject("First");
    await page.waitForURL(/\/p\/[0-9a-f-]+$/);
    await page.goto(`/o/${org.id}`);
    await projects.createProject("Second");
    await page.waitForURL(/\/p\/[0-9a-f-]+$/);
    await projects.expectProjectOverview("Second");
    await projects.switchProject("First");
    await projects.expectProjectOverview("First");
  });

  test("the sidebar collapses, persists, and expands", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Sidebar Org");
    await page.goto(`/o/${org.id}`);
    const projects = new ProjectsPage(page);
    await projects.expectOrganization("Sidebar Org");
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible(); // persisted
    await page.getByRole("button", { name: "Expand sidebar" }).click();
    await expect(projects.sidebar().getByText("Check catalog")).toBeVisible();
  });

  test("an outsider's organization URL sends the user back to their list", async ({ authedPage: page }) => {
    await page.goto("/o/00000000-0000-4000-8000-000000000000");
    await page.waitForURL(/\/organizations$/);
  });
});
