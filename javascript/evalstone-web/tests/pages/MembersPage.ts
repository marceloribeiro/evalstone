import { type Page, expect } from "@playwright/test";

/** /o/[oid]/members */
export class MembersPage {
  constructor(private page: Page) {}

  async goto(orgId: string) {
    await this.page.goto(`/o/${orgId}/members`);
    await expect(this.page.getByRole("heading", { level: 1, name: "Members" })).toBeVisible();
  }

  row(email: string) {
    return this.page.getByTestId(`member-${email}`);
  }

  async invite(email: string, role: "member" | "admin" = "member") {
    await this.page.getByLabel("Email").fill(email);
    if (role !== "member") {
      await this.page.getByRole("combobox", { name: "Invite as" }).click();
      await this.page.getByRole("option", { name: role }).click();
    }
    await this.page.getByRole("button", { name: "Invite" }).click();
  }

  invitation(email: string) {
    return this.page.getByTestId(`invitation-${email}`);
  }

  async setRole(email: string, role: "member" | "admin" | "owner") {
    await this.row(email).getByRole("combobox", { name: `Role of ${email}` }).click();
    await this.page.getByRole("option", { name: role, exact: true }).click();
    await expect(this.row(email)).toContainText(role); // a select for others, a badge once it is my own demoted row
  }

  /** Open the role select of a row, read the options it offers, close it again. */
  async roleOptions(email: string): Promise<string[]> {
    await this.row(email).getByRole("combobox", { name: `Role of ${email}` }).click();
    const listbox = this.page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    const names = await listbox.getByRole("option").allInnerTexts();
    await this.page.keyboard.press("Escape");
    await expect(listbox).toBeHidden();
    return names.map((n) => n.trim());
  }

  async remove(email: string) {
    await this.row(email).getByRole("button", { name: "Remove" }).click();
    await this.page.getByRole("dialog").getByRole("button", { name: "Remove" }).click();
    await expect(this.row(email)).toHaveCount(0);
  }
}
