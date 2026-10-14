import { test, expect } from "../fixtures/auth";
import { authed, inviteMember, newDataset, newOrganization, newProject, newQueue, newUser, pushRun, pushVersion } from "../fixtures/api";
import { LabelingPage } from "../pages/LabelingPage";
import { LoginPage } from "../pages/LoginPage";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const REPORT = JSON.parse(readFileSync(join(__dirname, "../../../../python/evalstone-api/tests/fixtures/rag-bot-ci-report.json"), "utf8"));

function variant(id: string) {
  const r = JSON.parse(JSON.stringify(REPORT));
  r.id = id;
  for (const x of r.results) x.output = { ...x.output, value: `${x.output.value} (v2)` };
  return r;
}

test.describe("Labeling", () => {
  test("an admin creates a grade queue from a run's failures and labels it from the keyboard", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Label Org");
    const project = await newProject(seed, org.id, "Label Project");
    await pushRun(seed, project.id, REPORT);
    const labeling = new LabelingPage(page);
    await labeling.goto(org.id, project.id);
    await expect(page.getByText("No queues yet")).toBeVisible();
    await labeling.newGradeQueue("must_include failures", REPORT.id, { check: "must_include", failedOnly: true, instructions: "Does the answer contain the required facts?" });
    await expect(page.getByTestId("instructions")).toContainText("required facts");
    await expect(labeling.progress()).toContainText("5"); // 5 failed must_include samples

    await labeling.startLabeling();
    await expect(labeling.task()).toContainText("fail"); // the machine verdict is shown
    await labeling.verdict(["4", "Enter"]); // grade 4 of 5
    await expect(labeling.counter()).toHaveText("1 of 5 done");
    // a skip is terminal: one S only arms it, a second S within a few seconds skips
    const armedOn = await labeling.currentTaskId();
    await page.keyboard.press("s");
    await expect(page.getByRole("button", { name: "Press again to skip (S)" })).toBeVisible();
    expect(await labeling.currentTaskId()).toBe(armedOn);
    await labeling.verdict(["s"]);
    await expect(labeling.counter()).toHaveText("2 of 5 done");
    // notes: typing in the box must not trigger the hotkeys; ⌘/Ctrl+Enter submits from it
    await page.keyboard.press("n");
    await page.getByLabel("Notes").pressSequentially("snafu");
    await expect(page.getByLabel("Notes")).toHaveValue("snafu");
    await page.keyboard.press("Escape");
    await labeling.verdict(["2", "Enter"]);
    await labeling.verdict(["5", "Enter"]);
    await labeling.verdict(["1", "Enter"]);
    await labeling.expectDone();

    await page.goto(`/o/${org.id}/p/${project.id}/labeling`);
    await labeling.openQueue("must_include failures");
    await expect(labeling.tasks().getByRole("row").filter({ hasText: /done/ })).toHaveCount(4);
    await expect(labeling.tasks().getByRole("row").filter({ hasText: /skipped/ })).toHaveCount(1);
    const labels = (await authed(seed, "get", `/projects/${project.id}/labels`)) as { items?: unknown[] } | unknown[];
    expect(Array.isArray(labels) ? labels.length : labels.items?.length).toBe(4);
  });

  test("compare and verify queues take A/B/T and P/F verdicts", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "AB Org");
    const project = await newProject(seed, org.id, "AB Project");
    const a = await pushRun(seed, project.id, REPORT);
    const b = await pushRun(seed, project.id, variant("ba328f946ccb"));
    const cmp = await newQueue(seed, project.id, { name: "v1 vs v2", kind: "compare", source: { run_a: a.id, run_b: b.id } });
    const ds = await newDataset(seed, project.id, "golden");
    await pushVersion(seed, project.id, ds.id, [{ id: "q1", input: "2+2?", expected: "4" }, { id: "q2", input: "capital of France", expected: "Lyon" }]);
    const ver = await newQueue(seed, project.id, { name: "check golden", kind: "verify", source: { dataset_id: ds.id, version: 1 } });
    expect(cmp.task_count).toBe(10);
    expect(ver.task_count).toBe(2);

    const labeling = new LabelingPage(page);
    await labeling.gotoQueue(org.id, project.id, cmp.id, "v1 vs v2");
    await labeling.startLabeling();
    await expect(page.getByTestId("output-b")).toContainText("(v2)");
    // a verdict chosen with the mouse leaves focus on that button: Enter there must not also fire the hotkey
    await page.getByRole("button", { name: "B is better (B)" }).click();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "B is better (B)" })).toHaveAttribute("aria-pressed", "true");
    const before = await labeling.currentTaskId();
    await page.getByRole("button", { name: "Submit (Enter)" }).click();
    await expect.poll(async () => labeling.currentTaskId()).not.toBe(before);
    await expect(labeling.counter()).toHaveText("1 of 10 done");
    await labeling.verdict(["t", "Enter"]);
    await expect(labeling.counter()).toHaveText("2 of 10 done");

    await labeling.gotoQueue(org.id, project.id, ver.id, "check golden");
    await labeling.startLabeling();
    await expect(labeling.task()).toContainText("2+2?");
    await labeling.verdict(["p", "Enter"]);
    await expect(labeling.task()).toContainText("Lyon");
    await labeling.verdict(["f", "Enter"]);
    await labeling.expectDone();
  });

  test("assignment hands a member their tasks first; a closed queue cannot be labeled; members cannot create queues", async ({ page, seed }) => {
    const org = await newOrganization(seed, "Assign Org");
    const project = await newProject(seed, org.id, "Assign Project");
    await pushRun(seed, project.id, REPORT);
    const member = await newUser("labeler");
    await inviteMember(seed, org.id, member.email);
    const run = (await authed(seed, "get", `/projects/${project.id}/runs`)) as { items: { id: string }[] };
    const q = await newQueue(seed, project.id, { name: "all samples", kind: "grade", source: { run_id: run.items[0].id }, scale: 2 });
    await authed(seed, "post", `/projects/${project.id}/label-queues/${q.id}/assign`, { user_ids: [member.id] });

    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(member.email, member.password);
    await page.waitForURL(/\/organizations$/);
    const labeling = new LabelingPage(page);
    await labeling.goto(org.id, project.id);
    await expect(page.getByRole("button", { name: "New queue" })).toHaveCount(0);
    await labeling.openQueue("all samples");
    await expect(page.getByRole("button", { name: "Close queue" })).toHaveCount(0);
    await expect(labeling.progress()).toContainText("10");
    await labeling.startLabeling();
    await labeling.verdict(["p", "Enter"]);
    await expect(labeling.counter()).toHaveText("1 of 10 done");

    await authed(seed, "patch", `/projects/${project.id}/label-queues/${q.id}`, { status: "closed" });
    await page.reload();
    await expect(page.getByTestId("load-error")).toContainText("closed");
    await labeling.gotoQueue(org.id, project.id, q.id, "all samples");
    await expect(page.getByRole("button", { name: "Label", exact: true })).toBeDisabled();
    await member.api.dispose();
  });
});
