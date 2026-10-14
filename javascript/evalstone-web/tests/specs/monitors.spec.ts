import { test, expect } from "../fixtures/auth";
import { inviteMember, newCheck, newOrganization, newProject, newUser, pushTraces } from "../fixtures/api";
import { MonitorsPage } from "../pages/MonitorsPage";
import { LoginPage } from "../pages/LoginPage";

const traces = (n: number, start = 0, bad: number[] = []) =>
  Array.from({ length: n }, (_, i) => i + start).map((i) => ({ id: `t${i}`, input: `question ${i}`, output: bad.includes(i) ? "no idea" : `Paris is the answer ${i}`, tags: ["prod"], latency_ms: 12.5 }));

test.describe("Monitors and alerts", () => {
  test("an admin creates a monitor over a catalog check; scoring opens an alert, recovery resolves it; pause and delete", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Monitor Org");
    const project = await newProject(seed, org.id, "Monitor Project");
    await newCheck(seed, org.id, "has-paris", "contains", { needles: ["Paris"] });
    const monitors = new MonitorsPage(page);
    await monitors.goto(org.id, project.id);
    await expect(page.getByText("No monitors yet")).toBeVisible();
    await monitors.createMonitor("prod answers", ["has-paris"], { sample: "100", threshold: "90", window: "60", minN: "10" });
    await expect(monitors.status()).toHaveText("active");
    await expect(monitors.window()).toContainText("0"); // nothing scored yet
    await expect(monitors.traces()).toContainText("No traces yet");

    await pushTraces(seed, project.id, traces(20, 0, [1, 5, 9, 13]));
    await expect(page.getByTestId("traces-count")).toHaveText("20 traces"); // live on traces.stored
    await monitors.scoreNow(); // eager Celery in dev/CI: the pass runs before the POST returns
    await expect(monitors.window()).toContainText("80.0%");
    await expect(monitors.window()).toContainText("open · 80.0%");
    await expect(monitors.alertRows("open")).toHaveCount(1);

    await monitors.gotoAlerts(org.id, project.id);
    await expect(page.getByRole("heading", { level: 1, name: "Alerts" })).toBeVisible();
    await expect(page.getByText("1 open · 0 resolved")).toBeVisible();
    await expect(monitors.alerts()).toContainText("prod answers");
    await expect(monitors.alerts()).toContainText("80.0%");

    await pushTraces(seed, project.id, traces(40, 100));
    await monitors.goto(org.id, project.id);
    await monitors.openMonitor("prod answers");
    await monitors.scoreNow();
    await expect(monitors.window()).toContainText("93.3%"); // 56/60
    await expect(monitors.alertRows("resolved")).toHaveCount(1);
    await expect(monitors.alertRows("open")).toHaveCount(0);
    await expect(monitors.window()).toContainText("none");

    const flagged = await monitors.flagFirst();
    await page.getByRole("button", { name: "Flagged only" }).click();
    await expect(page.getByTestId("traces-count")).toHaveText("1 trace");
    await expect(monitors.traces().getByRole("button", { name: `Unflag trace ${flagged}` })).toBeVisible();

    await monitors.pause();
    await monitors.deleteMonitor();
    await expect(page.getByText("No monitors yet")).toBeVisible();
  });

  test("a member sees monitors and alerts but has no create, score, pause or delete", async ({ page, seed }) => {
    const org = await newOrganization(seed, "RO Monitor Org");
    const project = await newProject(seed, org.id, "RO Monitor Project");
    await newCheck(seed, org.id, "has-paris", "contains", { needles: ["Paris"] });
    const { authed } = await import("../fixtures/api");
    const m = (await authed(seed, "post", `/projects/${project.id}/monitors`, { name: "ro monitor", check_keys: ["has-paris"], sample_rate: 1, alert_policy: { threshold: 0.9, window_minutes: 60, min_n: 1 } })) as { id: string };
    await pushTraces(seed, project.id, traces(3, 0, [0]));
    await authed(seed, "post", `/projects/${project.id}/monitors/${m.id}/score`);
    const member = await newUser("viewer");
    await inviteMember(seed, org.id, member.email);
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn(member.email, member.password);
    await page.waitForURL(/\/organizations$/);
    const monitors = new MonitorsPage(page);
    await monitors.goto(org.id, project.id);
    await expect(page.getByRole("button", { name: "New monitor" })).toHaveCount(0);
    await monitors.openMonitor("ro monitor");
    await expect(monitors.window()).toContainText("66.7%");
    await expect(page.getByRole("button", { name: "Score now" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Pause" })).toHaveCount(0);
    await monitors.gotoAlerts(org.id, project.id);
    await expect(page.getByText("1 open · 0 resolved")).toBeVisible();
    await member.api.dispose();
  });
});
