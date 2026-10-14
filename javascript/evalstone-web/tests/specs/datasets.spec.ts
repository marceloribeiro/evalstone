import { test, expect } from "../fixtures/auth";
import { newDataset, newOrganization, newProject, pushVersion } from "../fixtures/api";
import { DatasetsPage } from "../pages/DatasetsPage";

const V1 = [
  { id: "return-window", input: "How many days do I have to return something?", expected: "30 days", tags: ["returns"] },
  { id: "free-shipping", input: "Is shipping free?", expected: "over $50", tags: ["shipping"] },
  { id: "warranty", input: "How long is the warranty?", expected: "2 years" },
];
const V2 = [
  V1[0],
  { ...V1[1], expected: "over $75" }, // changed
  // warranty removed
  { id: "ship-to-uk", input: "Do you ship to the UK?", expected: "no", tags: ["shipping", "edge"] }, // added
];

test.describe("Datasets", () => {
  test("create a dataset, see it listed, and browse its versions, samples and the diff between them", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Data Org");
    const project = await newProject(seed, org.id, "Data Project");
    const datasets = new DatasetsPage(page);
    await datasets.goto(org.id, project.id);
    await expect(page.getByText("No datasets yet")).toBeVisible();
    await datasets.createDataset("golden", "The hand-written answers", "golden, ci");
    await expect(datasets.tags()).toContainText("golden");
    await expect(page.getByText("No versions yet")).toBeVisible();

    const ds = (await (await seed.api.get(`/projects/${project.id}/datasets`, { headers: { Authorization: `Bearer ${seed.token}` } })).json()) as { id: string }[];
    await pushVersion(seed, project.id, ds[0].id, V1, "first");
    await pushVersion(seed, project.id, ds[0].id, V2, "second");
    await page.reload();
    await expect(datasets.versions()).toContainText("v2");
    await expect(datasets.versions().getByRole("row").filter({ hasText: "v2" })).toContainText("latest");
    await expect(page.getByRole("tab", { name: "Samples of v2" })).toBeVisible();
    await expect(datasets.samples()).toContainText("ship-to-uk");
    await expect(datasets.samples()).not.toContainText("warranty");
    await datasets.samples().getByRole("row").filter({ hasText: "free-shipping" }).click();
    await expect(page.getByTestId("sample-detail")).toContainText("over $75");

    await datasets.openDiff();
    await expect(page.getByRole("combobox", { name: "Diff against" })).toContainText("v1");
    await expect(datasets.diff()).toContainText("1 added");
    await expect(datasets.diff()).toContainText("1 removed");
    await expect(datasets.diff()).toContainText("1 changed");
    await expect(datasets.diff()).toContainText("1 unchanged");
    await expect(page.getByRole("table", { name: "Changed" })).toContainText("over $50");
    await expect(page.getByRole("table", { name: "Changed" })).toContainText("over $75");
    await expect(page.getByRole("table", { name: "Removed" })).toContainText("warranty");

    await datasets.chooseVersion(1);
    await datasets.openSamples(1); // the Diff tab was active
    await expect(datasets.samples()).toContainText("warranty");
    await datasets.openDiff();
    await expect(datasets.diff()).toContainText("1 removed"); // v1 relative to v2: ship-to-uk is gone
  });

  test("an admin tags a dataset (persisted across a reload) and deletes it", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Tag Org");
    const project = await newProject(seed, org.id, "Tag Project");
    await newDataset(seed, project.id, "nightly");
    const datasets = new DatasetsPage(page);
    await datasets.goto(org.id, project.id);
    await datasets.openDataset("nightly");
    await datasets.addTag("regression");
    await datasets.addTag("v2");
    await page.reload();
    await expect(datasets.tags()).toContainText("regression");
    await expect(datasets.tags()).toContainText("v2");
    await datasets.removeTag("regression");
    await page.reload();
    await expect(datasets.tags()).not.toContainText("regression");
    await datasets.deleteDataset();
    await expect(page.getByText("No datasets yet")).toBeVisible();
  });

  test("a member sees tags but cannot edit or delete", async ({ page, seed }) => {
    const { newUser, inviteMember } = await import("../fixtures/api");
    const { LoginPage } = await import("../pages/LoginPage");
    const org = await newOrganization(seed, "RO Org");
    const project = await newProject(seed, org.id, "RO Project");
    await newDataset(seed, project.id, "golden", { tags: ["ci"] });
    const member = await newUser("member");
    await inviteMember(seed, org.id, member.email);
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(member.email, member.password);
    await page.waitForURL(/\/organizations$/);
    const datasets = new DatasetsPage(page);
    await datasets.goto(org.id, project.id);
    await datasets.openDataset("golden");
    await expect(datasets.tags()).toContainText("ci");
    await expect(page.getByLabel("Add tag")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Delete dataset" })).toHaveCount(0);
    await member.api.dispose();
  });
});
