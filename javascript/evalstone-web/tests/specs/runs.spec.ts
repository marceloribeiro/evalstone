import { test, expect } from "../fixtures/auth";
import { newOrganization, newProject, pushRun } from "../fixtures/api";
import { RunsPage } from "../pages/RunsPage";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const REPORT = JSON.parse(readFileSync(join(__dirname, "../../../../python/evalstone-api/tests/fixtures/rag-bot-ci-report.json"), "utf8"));

/** The same report pushed again under a new id, with one passing result flipped to a failure. */
function regressed() {
  const r = JSON.parse(JSON.stringify(REPORT));
  r.id = "ba328f946ccb";
  const flip = r.results.find((x: { check_key: string; score: { passed: boolean } }) => x.check_key === "no_apology" && x.score.passed);
  flip.score = { ...flip.score, value: 0, passed: false, reason: "apologised twice" };
  r.summary.passed -= 1;
  r.summary.pass_rate = r.summary.passed / r.summary.results;
  return r;
}

test.describe("Runs", () => {
  test("the list shows pushed runs, filters by suite, and opens a run with its per-check table and results", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Runs Org");
    const project = await newProject(seed, org.id, "Runs Project");
    await pushRun(seed, project.id, REPORT);
    const runs = new RunsPage(page);
    await runs.goto(org.id, project.id);
    await expect(runs.table()).toContainText(REPORT.id);
    await expect(runs.table()).toContainText("87.5%");
    await expect(runs.table()).toContainText("PASS");
    await runs.filterSuite("ci");
    await expect(runs.table()).toContainText(REPORT.id);

    await runs.openRun(REPORT.id);
    await expect(runs.checkRow("must_include")).toContainText("50.0%");
    await expect(runs.checkRow("no_apology")).toContainText("100.0%");
    await expect(page.getByRole("list", { name: "Gate lines" })).toContainText("PASS pass rate 87.5%");
    await expect(runs.resultsCount()).toHaveText("40 results");
    await runs.toggleFailedOnly();
    await expect(runs.resultsCount()).toHaveText("5 results");
    await runs.filterCheck("must_include");
    await expect(runs.resultsCount()).toHaveText("5 results");
    await runs.expandFirstResult();
    await expect(page.getByTestId("result-detail")).toContainText("Input");
  });

  test("a run arriving while the list is open appears without a reload", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Live Runs Org");
    const project = await newProject(seed, org.id, "Live Runs Project");
    const runs = new RunsPage(page);
    await runs.goto(org.id, project.id);
    await expect(page.getByText("No runs stored yet")).toBeVisible();
    await pushRun(seed, project.id, REPORT);
    await expect(runs.table()).toContainText(REPORT.id);
  });

  test("set a baseline, then the next run's Compare tab shows the regression against it", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Compare Org");
    const project = await newProject(seed, org.id, "Compare Project");
    await pushRun(seed, project.id, REPORT);
    const runs = new RunsPage(page);
    await runs.goto(org.id, project.id);
    await runs.openRun(REPORT.id);
    await runs.setBaseline();

    const second = regressed();
    await pushRun(seed, project.id, second);
    await runs.goto(org.id, project.id);
    await expect(runs.table().getByRole("row").filter({ hasText: REPORT.id })).toContainText("Baseline");
    await runs.openRun(second.id);
    await runs.openCompare();
    await expect(page.getByRole("combobox", { name: "Compare against" })).toContainText(`${REPORT.id} (baseline)`);
    await expect(runs.comparison()).toContainText("-2.5%"); // 87.5% → 85.0%
    await expect(page.getByRole("table", { name: "Regressions" })).toContainText("no_apology");
    await expect(page.getByRole("table", { name: "Regressions" })).toContainText("apologised twice");
    await expect(page.getByRole("table", { name: "Improvements" })).toHaveCount(0);
  });
});
