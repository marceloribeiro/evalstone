import { test, expect } from "../fixtures/auth";
import { authed, newOrganization, newProject, newUser, registerUser } from "../fixtures/api";
import { request } from "@playwright/test";
import { API_URL } from "../fixtures/api";
import { MembersPage } from "../pages/MembersPage";
import { SettingsPage } from "../pages/SettingsPage";
import { LoginPage } from "../pages/LoginPage";

test.describe("Members, invitations and project settings", () => {
  test("an owner invites, promotes, demotes and removes; a pending invitation is revoked", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "People Org");
    const members = new MembersPage(page);
    await members.goto(org.id);
    await expect(members.row(seed.email)).toContainText("you");
    await expect(members.row(seed.email)).toContainText("owner");

    // an existing user joins at once
    const colleague = await newUser("colleague");
    await members.invite(colleague.email);
    await expect(members.row(colleague.email)).toContainText("member");
    await expect(page.getByText("No pending invitations.")).toBeVisible();
    // a stranger stays pending until they register
    const newcomerEmail = `newcomer-${Date.now()}@example.com`;
    await members.invite(newcomerEmail, "admin");
    await expect(members.invitation(newcomerEmail)).toContainText("admin");
    const api = await request.newContext({ baseURL: API_URL });
    const newcomer = await registerUser(api, newcomerEmail);
    await page.reload();
    await expect(members.row(newcomerEmail)).toContainText("admin");
    await expect(members.invitation(newcomerEmail)).toHaveCount(0);

    await members.setRole(colleague.email, "admin");
    await members.setRole(colleague.email, "member");
    // the owner's role select offers ownership; an admin's does not (checked below as the colleague)
    expect(await members.roleOptions(colleague.email)).toEqual(["member", "admin", "owner"]);

    const ghostEmail = `ghost-${Date.now()}@example.com`;
    await members.invite(ghostEmail);
    await members.invitation(ghostEmail).getByRole("button", { name: "Revoke" }).click();
    await expect(members.invitation(ghostEmail)).toHaveCount(0);
    await members.remove(colleague.email);
    await colleague.api.dispose();
    await newcomer.api.dispose();
  });

  test("an admin edits roles below owner only; a member sees the list read-only", async ({ page, seed }) => {
    const org = await newOrganization(seed, "Roles Org");
    const admin = await newUser("admin");
    const member = await newUser("member");
    await authed(seed, "post", `/organizations/${org.id}/invitations`, { email: admin.email, role: "admin" });
    await authed(seed, "post", `/organizations/${org.id}/invitations`, { email: member.email, role: "member" });
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(admin.email, admin.password);
    await page.waitForURL(/\/organizations$/);
    const members = new MembersPage(page);
    await members.goto(org.id);
    await expect(members.row(seed.email).getByRole("combobox")).toHaveCount(0); // the owner's row is not editable by an admin
    await expect(members.row(seed.email)).toContainText("owner");
    expect(await members.roleOptions(member.email)).toEqual(["member", "admin"]);
    await expect(page.getByRole("button", { name: "Invite" })).toBeVisible();

    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL(/\/login$/);
    await login.signIn(member.email, member.password);
    await page.waitForURL(/\/(organizations|o\/)/); // this browser remembers the last organization: sign-in lands there
    await members.goto(org.id);
    await expect(members.row(seed.email)).toContainText("owner");
    await expect(page.getByRole("table", { name: "Members" }).getByRole("combobox")).toHaveCount(0); // the sidebar switcher is a combobox too
    await expect(page.getByRole("button", { name: "Remove" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Invite" })).toHaveCount(0);
    await admin.api.dispose();
    await member.api.dispose();
  });

  test("project settings: rename reaches the sidebar, keys are minted and revoked, the project is deleted", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Settings Org");
    const project = await newProject(seed, org.id, "old name");
    const settings = new SettingsPage(page);
    await settings.goto(org.id, project.id);
    await settings.rename("new name");
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("new name");
    await settings.mintKey("ci");
    await settings.revokeKey("ci");
    await expect(settings.key("ci").getByRole("button", { name: "Revoke" })).toHaveCount(0);
    await settings.deleteProject();
    await page.waitForURL(new RegExp(`/o/${org.id}$`));
    await expect(page.getByRole("list", { name: "Projects" })).toHaveCount(0);
    await expect(page.getByText("No projects yet")).toBeVisible();
  });
});
