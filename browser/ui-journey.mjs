import { chromium } from "playwright";
const [origin, screenshot] = process.argv.slice(2);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1480, height: 1100 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(origin);
  await page.getByLabel("Bundled page").selectOption("07-form-control");
  await page.getByRole("button", { name: "Scan and repair" }).click();
  await page.waitForURL("**/runs/**");
  await page
    .locator("#run-status")
    .filter({ hasText: /^accepted$/ })
    .waitFor({ timeout: 80000 });
  await page.getByRole("link", { name: "Candidate 1: rejected" }).waitFor();
  await page.getByRole("link", { name: "Candidate 2: accepted" }).waitFor();
  if ((await page.locator("img").count()) !== 2)
    throw Error("Missing before/after screenshots");
  if (!(await page.locator(".diff").textContent()).includes('type="button"'))
    throw Error("Missing actual diff");
  await page.screenshot({ path: screenshot, fullPage: true });
  await page.getByRole("link", { name: "Candidate 1: rejected" }).click();
  await page
    .locator(".panel")
    .filter({ hasText: "Candidate decision" })
    .filter({ hasText: "rejected" })
    .waitFor();
  if (errors.length) throw Error(errors.join(", "));
  console.log(
    "PASS: real UI creates run, shows rejected and accepted candidates, screenshots and diff",
  );
} finally {
  await browser.close();
}
