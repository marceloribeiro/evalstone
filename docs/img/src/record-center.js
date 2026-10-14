// Records the center half of the walkthrough against a LOCAL center (web :8292 → API :8281).
// Usage: node record-center.js <web-node_modules> <video-dir>
// Env: DEMO_EMAIL, DEMO_PASSWORD, ORG_ID, PROJECT_ID, RUN_ID (a judged run), QUEUE_ID (a grade queue over it).
const path = require("path");
const { chromium } = require(path.join(process.argv[2], "playwright"));
const VIDEO_DIR = process.argv[3];
const WEB = process.env.WEB ?? "http://localhost:8182";
const BASE = `${WEB}/o/${process.env.ORG_ID}/p/${process.env.PROJECT_ID}`;
const RUN = process.env.RUN_ID;
const QUEUE = process.env.QUEUE_ID;
const GRADES = {
  "delete-account": 5, express: 1, "free-shipping": 5, "refund-time": 1, "return-window": 5,
  "sale-return": 2, "ship-to-uk": 1, "shipping-time": 5, warranty: 5, "warranty-claim": 1,
};
const SIZE = { width: 1280, height: 720 };

(async () => {
  const browser = await chromium.launch();
  // sign in off camera
  const login = await browser.newContext({ viewport: SIZE });
  const lp = await login.newPage();
  await lp.goto(`${WEB}/login`);
  await lp.getByLabel("Email").fill(process.env.DEMO_EMAIL);
  await lp.getByLabel("Password").fill(process.env.DEMO_PASSWORD);
  await lp.getByRole("button", { name: "Sign in" }).click();
  await lp.waitForURL((u) => !u.pathname.startsWith("/login"));
  const state = await login.storageState();
  await login.close();

  const ctx = await browser.newContext({ viewport: SIZE, storageState: state, recordVideo: { dir: VIDEO_DIR, size: SIZE } });
  const page = await ctx.newPage();
  const pause = (ms) => page.waitForTimeout(ms);

  // 1. the judged run the CLI pushed: per-check table, gate, the judge's reasons
  await page.goto(`${BASE}/runs/${RUN}`);
  await page.getByRole("table").last().waitFor();
  await pause(2500);
  await page.mouse.wheel(0, 420);
  await pause(3000);

  // 2. a person grades the judge's outputs from the keyboard
  await page.goto(`${BASE}/labeling/${QUEUE}/label`);
  for (let i = 0; i < 10; i++) {
    const counter = page.getByTestId("counter");
    await page.getByTestId("task").waitFor();
    const before = await counter.innerText();
    const text = await page.getByTestId("task").innerText().catch(() => "");
    const header = await page.locator("main").innerText();
    const key = (header.match(/Sample\s+(\S+)/) || [])[1];
    if (!(key in GRADES)) throw new Error(`unknown sample ${key} (${text.slice(0, 60)})`);
    await pause(i < 2 ? 1400 : 600);
    await page.keyboard.press(String(GRADES[key]));
    await pause(350);
    await page.keyboard.press("Enter");
    // the counter ("N of 10 done") moves once the answer is stored; the last one shows queue-done
    await page.waitForFunction(
      (prev) => {
        const c = document.querySelector('[data-testid="counter"]');
        return !!document.querySelector('[data-testid="queue-done"]') || (c && c.innerText !== prev);
      },
      before,
    );
    await page.waitForFunction(
      (k) => !!document.querySelector('[data-testid="queue-done"]') ||
        (document.querySelector('[data-testid="task"]') && !document.querySelector("main").innerText.includes(`Sample ${k} ·`)),
      key,
    );
  }
  await page.getByTestId("queue-done").waitFor();
  await pause(1500);

  // 3. calibrate the judge against those labels, then Promote it
  await page.goto(`${BASE}/judges`);
  await page.getByRole("table", { name: "Judges seen" }).waitFor();
  await pause(1500);
  await page.getByRole("table", { name: "Judges seen" }).getByRole("row").filter({ hasText: "helpful" }).getByRole("button", { name: "Calibrate" }).click();
  await pause(900);
  await page.getByRole("dialog").getByRole("button", { name: "Run calibration" }).click();
  const row = page.getByRole("table", { name: "Calibrations" }).getByRole("row").filter({ hasText: "helpful" }).first();
  await row.getByRole("button", { name: "Promote" }).waitFor({ timeout: 30000 });
  await page.getByRole("table", { name: "Calibrations" }).scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 200);
  await pause(3000);
  await row.getByRole("button", { name: "Promote" }).click();
  await row.getByRole("button", { name: "Promoted" }).waitFor();
  await pause(3000);

  await ctx.close(); // flushes the video
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
