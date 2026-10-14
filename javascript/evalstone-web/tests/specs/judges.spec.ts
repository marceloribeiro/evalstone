import { test, expect } from "../fixtures/auth";
import { authed, labelQueue, newOrganization, newProject, newProvider, newQueue, pushRun } from "../fixtures/api";
import { judgedReport, JUDGE_VERSION } from "../fixtures/judged";
import { ProvidersPage } from "../pages/ProvidersPage";
import { JudgesPage } from "../pages/JudgesPage";

test.describe("Providers and judges", () => {
  test("an admin adds a provider, tests it (the failure is reported, never the key), edits and deletes it", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Provider Org");
    const providers = new ProvidersPage(page);
    await providers.goto(org.id);
    await expect(page.getByText("No providers yet")).toBeVisible();
    // a loopback port nothing listens on: the test call fails at once, with no network (PROVIDER_ALLOW_PRIVATE_URLS=true)
    await providers.addProvider("router", "sk-or-v1-secret-9876", "http://127.0.0.1:9/v1");
    await expect(providers.row("router")).toContainText("…9876");
    await expect(providers.row("router")).not.toContainText("secret");
    await expect(providers.row("router")).toContainText("never tested");

    await providers.test("router", "meta/llama");
    await expect(providers.row("router").getByTestId("test-result")).toContainText("failed");
    await expect(providers.row("router")).toContainText("failed"); // verified_ok stamped on the row
    await expect(providers.row("router").getByTestId("last-error")).toBeVisible();
    await expect(page.locator("body")).not.toContainText("sk-or-v1");

    await providers.removeKey("router");
    await expect(providers.row("router")).toContainText("none");
    await expect(providers.row("router").getByTestId("test-result")).toHaveCount(0); // the old result does not outlive the edit
    await providers.deleteProvider("router");
    await expect(providers.row("router")).toHaveCount(0);
  });

  test("judge settings resolve to the organization's providers; a judge is calibrated against labels and promoted", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Judge Org");
    const project = await newProject(seed, org.id, "Judge Project");
    await newProvider(seed, org.id, { name: "local", adapter: "openai", api_key: "sk-local", base_url: "http://127.0.0.1:9/v1" });
    // the judge fails two samples; the humans fail one of those and one the judge passed → 8/10 agree
    const run = await pushRun(seed, project.id, judgedReport("judge0000001", { judgeFails: ["express", "refund-time"] }));
    const queue = await newQueue(seed, project.id, { name: "grade helpful", kind: "grade", source: { run_id: run.id }, check_key: "helpful", scale: 5 });
    await labelQueue(seed, project.id, queue.id, (key) => (key === "express" || key === "sale-return" ? 1 : 5));

    const judges = new JudgesPage(page);
    await judges.goto(org.id, project.id);
    await expect(judges.settings()).toContainText("none");
    await judges.setDefaultModel("local/tiny");
    await page.reload();
    await expect(judges.settings()).toContainText("local/tiny");
    // a model whose provider the organization does not have is refused by the API, shown as a toast
    await page.getByRole("button", { name: "Edit judge settings" }).click();
    await page.getByLabel("Default model").fill("nowhere/model");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.locator("[data-sonner-toast]").first()).toContainText("no provider named");
    await page.getByRole("button", { name: "Cancel" }).click();

    // a value typed in the Calibrate dialog and abandoned does not carry over to the next opening
    await judges.judges().getByRole("row").filter({ hasText: "helpful" }).getByRole("button", { name: "Calibrate" }).click();
    await page.getByRole("dialog").getByLabel(/Labels under check/).fill("stale-value");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await judges.judges().getByRole("row").filter({ hasText: "helpful" }).getByRole("button", { name: "Calibrate" }).click();
    await expect(page.getByRole("dialog").getByLabel(/Labels under check/)).toHaveValue("helpful");
    await page.keyboard.press("Escape");

    await expect(judges.judges()).toContainText("helpful");
    await expect(judges.judges()).toContainText(JUDGE_VERSION);
    await expect(judges.judges().getByRole("row").filter({ hasText: "helpful" })).toContainText("10");
    await judges.calibrate("helpful"); // label_check defaults to the check key
    const row = judges.calibrationRow("helpful");
    await expect(row).toContainText("done");
    await expect(row).toContainText("80.0%");
    await row.click();
    await expect(page.getByTestId("confusion")).toContainText("Both pass");
    await judges.promote("helpful");
    await expect(judges.settings().getByRole("list", { name: "Overrides" })).toContainText("helpful → local/tiny");
    const saved = (await authed(seed, "get", `/projects/${project.id}/judge-settings`)) as { overrides: Record<string, string> };
    expect(saved.overrides).toEqual({ helpful: "local/tiny" });

    // the settings form applies its edits on top of the live row: an override written while it was open survives Save
    await page.getByRole("button", { name: "Edit judge settings" }).click();
    await authed(seed, "put", `/projects/${project.id}/judge-settings`, { default_model: "local/tiny", overrides: { helpful: "local/tiny", grounded: "local/tiny" } });
    await page.getByLabel("Default model").fill("local/large");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(judges.settings()).toContainText("local/large");
    await expect(judges.settings().getByRole("list", { name: "Overrides" })).toContainText("grounded → local/tiny");
    // two rows for the same check are refused before anything is sent
    await page.getByRole("button", { name: "Edit judge settings" }).click();
    await page.getByRole("button", { name: "Add override" }).click();
    const n = await page.getByLabel(/Override \d+ check/).count();
    await page.getByLabel(`Override ${n} check`).fill("helpful");
    await page.getByLabel(`Override ${n} model`).fill("local/other");
    await expect(page.getByRole("alert").filter({ hasText: "appears twice" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
    await page.getByRole("button", { name: "Cancel" }).click();

    // a calibration against labels that do not exist is accepted, then marked failed with the reason on its row
    await judges.calibrate("helpful", "nonexistent");
    const failed = judges.calibrations().getByRole("row").filter({ hasText: "failed" });
    await expect(failed).toHaveCount(1);
    await failed.click();
    await expect(page.getByTestId("calibration-error")).toContainText("no human labels");
    await expect(failed.getByRole("button", { name: "Promote" })).toHaveCount(0);
  });
});
