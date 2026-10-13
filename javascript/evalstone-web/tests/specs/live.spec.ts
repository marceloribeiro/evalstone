import { test, expect } from "../fixtures/auth";
import { API_URL, authed, newOrganization, newProject } from "../fixtures/api";
import { ProjectsPage } from "../pages/ProjectsPage";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const REPORT = JSON.parse(readFileSync(join(__dirname, "../../../../python/evalstone-api/tests/fixtures/rag-bot-ci-report.json"), "utf8"));

test.describe("Live updates", () => {
  test("the project home goes Live and a run pushed through the API appears in the feed and the runs table", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Live Org");
    const project = await newProject(seed, org.id, "Live Project");
    await page.goto(`/o/${org.id}/p/${project.id}`);
    const projects = new ProjectsPage(page);
    await projects.expectProjectOverview("Live Project");
    await projects.expectLive();
    await expect(page.getByText("No runs stored yet")).toBeVisible();

    const key = await projects.createIngestKey("ci");
    // the key the UI minted works against the API, as the CLI would use it
    const res = await seed.api.post(`${API_URL}/projects/${project.id}/runs`, { data: REPORT, headers: { Authorization: `Bearer ${key}` } });
    expect(res.status()).toBe(201);

    await expect(projects.liveFeed()).toContainText("run.stored");
    await expect(projects.liveFeed()).toContainText("ci · 88% · 40 results");
    await expect(page.getByRole("table", { name: "Latest runs" })).toContainText(REPORT.id); // reloaded on the event
  });

  test("events for another project do not show here", async ({ authedPage: page, seed }) => {
    const org = await newOrganization(seed, "Scoped Org");
    const a = await newProject(seed, org.id, "A");
    const b = await newProject(seed, org.id, "B");
    await page.goto(`/o/${org.id}/p/${a.id}`);
    const projects = new ProjectsPage(page);
    await projects.expectLive();
    await authed(seed, "post", `/projects/${b.id}/runs`, REPORT);
    await authed(seed, "post", `/projects/${a.id}/labels`, { labels: [{ sample_id: "s", output_hash: "0000000000000000", value: 1, passed: true }] });
    await expect(projects.liveFeed()).toContainText("labels.stored");
    await expect(projects.liveFeed()).not.toContainText("run.stored");
  });
});
