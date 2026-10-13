import { test, expect } from "../fixtures/auth";
import { newOrganization, newProject, newUser, inviteMember } from "../fixtures/api";
import { LoginPage } from "../pages/LoginPage";
import { ProjectsPage } from "../pages/ProjectsPage";

const TOKEN_KEY = "evalstone.token";

test.describe("Session and API failures", () => {
  test("an expired session mid-page sends the user to /login instead of retrying forever", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Expiry Org");
    const project = await newProject(seed, org.id, "Expiry Project");
    // the first request made with the stored token after it expired: the ws ticket
    await page.route("**/ws-ticket", (route) =>
      route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "invalid token" }) }),
    );
    await page.goto(`/o/${org.id}/p/${project.id}`);
    await page.waitForURL(/\/login$/);
    expect(await page.evaluate((k) => localStorage.getItem(k), TOKEN_KEY)).toBeNull();
  });

  test("the center being unreachable keeps the session and offers a retry", async ({ authedPage: page }) => {
    let outages = 0;
    await page.route("**/me", async (route) => {
      if (outages < 1) {
        outages += 1;
        await route.fulfill({ status: 502, contentType: "text/html", body: "<html><body>502 Bad Gateway</body></html>" });
      } else await route.fallback();
    });
    await page.reload();
    await expect(page.getByRole("main")).toContainText("not reachable");
    expect(await page.evaluate((k) => localStorage.getItem(k), TOKEN_KEY)).not.toBeNull(); // the token survived the blip
    await page.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByRole("heading", { name: "Organizations" })).toBeVisible();
  });

  test("a non-JSON error body surfaces its status, not a parse error", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Gateway Org");
    const project = await newProject(seed, org.id, "Gateway Project");
    await page.route("**/runs?*", (route) =>
      route.fulfill({ status: 502, contentType: "text/html", body: "<html><body>502 Bad Gateway</body></html>" }),
    );
    await page.goto(`/o/${org.id}/p/${project.id}`);
    const toast = page.locator("[data-sonner-toast]").first();
    await expect(toast).toContainText("502");
    await expect(toast).not.toContainText("Unexpected token");
  });

  test("a plain member sees the project home without the ingest-key form and without a 403 toast", async ({ page, seed }) => {
    const org = await newOrganization(seed, "Member Org");
    const project = await newProject(seed, org.id, "Member Project");
    const member = await newUser("member");
    await inviteMember(seed, org.id, member.email);
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(member.email, member.password);
    await page.waitForURL(/\/organizations$/);
    await page.goto(`/o/${org.id}/p/${project.id}`);
    await new ProjectsPage(page).expectProjectOverview("Member Project");
    await expect(page.getByText("Ask an organization admin for an ingest key.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Create ingest key" })).toHaveCount(0);
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0);
    await member.api.dispose();
  });
});
