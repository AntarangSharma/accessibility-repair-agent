import fs from "node:fs/promises";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

// This process accepts paths from the Python coordinator, never browser URLs or code.
const repository = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const input = JSON.parse(
  await new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
      if (data.length > 32768) process.exit(2);
    });
    process.stdin.on("end", () => resolve(data));
  }),
);
if (input.version !== 1 || !/^[0-9]{2}-[a-z-]+$/.test(input.fixture))
  throw Error("Invalid v1 input");
const root = await fs.realpath(input.root);
const contract = JSON.parse(
  await fs.readFile(
    path.join(repository, "fixtures", input.fixture, "contract.json"),
    "utf8",
  ),
);
const files = new Map();
for (const name of ["index.html", "style.css", "trusted.js"]) {
  const resolved = await fs.realpath(path.join(root, name));
  if (path.dirname(resolved) !== root) throw Error("Symlink escape");
  files.set("/" + name, await fs.readFile(resolved));
}
const trusted = await fs.readFile(
  path.join(repository, "fixtures", input.fixture, "trusted.js"),
);
if (!files.get("/trusted.js").equals(trusted)) throw Error("Untrusted script");
const types = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "text/javascript",
};
const server = http.createServer((req, res) => {
  const name = req.url === "/" ? "/index.html" : req.url;
  if (req.method !== "GET" || !files.has(name)) {
    res.writeHead(404);
    res.end();
    return;
  }
  res.writeHead(200, {
    "Content-Type": types[path.extname(name)],
    "Content-Security-Policy":
      "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
  });
  res.end(files.get(name));
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
const deadline = setTimeout(() => process.exit(3), 55000);
try {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1100, height: 800 },
    serviceWorkers: "block",
  });
  const blocked = [];
  await context.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (
      url.origin !== origin ||
      !["/", "/index.html", "/style.css", "/trusted.js"].includes(url.pathname)
    ) {
      blocked.push(url.origin + url.pathname);
      return route.abort();
    }
    if (
      route.request().resourceType() === "script" &&
      url.pathname !== "/trusted.js"
    )
      return route.abort();
    return route.continue();
  });
  const load = async () => {
    const page = await context.newPage();
    page.setDefaultTimeout(2500);
    await page.goto(origin + "/index.html", { waitUntil: "networkidle" });
    return page;
  };
  const page = await load();
  // The full scoped scan remains visible alongside the narrower repair rules.
  const full = await new AxeBuilder({ page })
    .include("main")
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const targeted = await new AxeBuilder({ page })
    .include("main")
    .withRules(["label", "color-contrast"])
    .analyze();
  const compact = (results) =>
    results.map((v) => ({
      id: v.id,
      impact: v.impact,
      description: v.description,
      helpUrl: v.helpUrl,
      nodes: v.nodes.map((n) => ({
        target: n.target,
        html: n.html,
        summary: n.failureSummary || "",
      })),
    }));
  const inspection = await page.evaluate(() => {
    const unsupported = [];
    const controls = [
      ...document.querySelectorAll("input, button, [data-action]"),
    ].map((el) => {
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      const parent = el.parentElement;
      const previous = el.previousElementSibling;
      const existing =
        el.labels?.length ||
        el.getAttribute("aria-label") ||
        el.getAttribute("aria-labelledby");
      const nearby = previous?.textContent?.trim() || "";
      const labelSupported = Boolean(
        existing ||
          (nearby &&
            nearby.length < 80 &&
            !previous.matches("input, button") &&
            parent.querySelectorAll("input").length === 1),
      );
      if (el.tagName === "INPUT" && !labelSupported)
        unsupported.push(`Ambiguous label for #${el.id}`);
      return {
        id: el.id,
        tag: el.tagName.toLowerCase(),
        name: el.getAttribute("name"),
        type: el.getAttribute("type"),
        text: el.textContent.trim(),
        nearby,
        labelSupported,
        visible:
          box.width > 0 &&
          box.height > 0 &&
          style.visibility !== "hidden" &&
          style.opacity !== "0",
        disabled: el.disabled || false,
        box: { x: box.x, y: box.y, width: box.width, height: box.height },
      };
    });
    const text = [...document.querySelectorAll("main *")]
      .filter((el) => el.children.length === 0 && el.textContent.trim())
      .map((el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        let ancestor = el;
        let background = style.backgroundColor;
        while (
          ancestor &&
          (background === "rgba(0, 0, 0, 0)" || background === "transparent")
        ) {
          ancestor = ancestor.parentElement;
          if (ancestor) background = getComputedStyle(ancestor).backgroundColor;
        }
        for (let a = el; a; a = a.parentElement) {
          if (getComputedStyle(a).backgroundImage !== "none")
            unsupported.push("Non-solid background requires manual review");
        }
        return {
          text: el.textContent.trim(),
          color: style.color,
          background,
          visible:
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== "hidden" &&
            style.opacity !== "0",
        };
      });
    if (
      document.querySelector(
        '[role="tab"], [role="slider"], [role="tree"], [contenteditable]',
      )
    )
      unsupported.push("Complex widget outside v1");
    return { controls, text, unsupported: [...new Set(unsupported)] };
  });
  await page.screenshot({ path: input.screenshot, fullPage: true });
  const labels = [];
  for (const [selector, expected] of Object.entries(contract.labels)) {
    const locator = page.locator(selector);
    const pass = await locator
      .evaluate((el, name) => {
        const labels = [...(el.labels || [])]
          .map((l) => l.textContent.trim())
          .join(" ");
        const aria =
          el.getAttribute("aria-label") ||
          (el.getAttribute("aria-labelledby") || "")
            .split(/\s+/)
            .map((id) => document.getElementById(id)?.textContent.trim() || "")
            .join(" ")
            .trim();
        return (aria || labels) === name;
      }, expected)
      .catch(() => false);
    labels.push({
      id: selector,
      pass,
      observation: pass
        ? "Expected accessible name preserved"
        : "Accessible name missing or incorrect",
    });
  }
  await page.close();
  const behavior = [];
  const keyboard = [];
  const check = async (destination, id, fn) => {
    const p = await load();
    try {
      await fn(p);
      destination.push({ id, pass: true, observation: "Passed" });
    } catch (error) {
      destination.push({
        id,
        pass: false,
        observation: String(error.message).slice(0, 450),
      });
    } finally {
      await p.close();
    }
  };
  const assert = (condition, message) => {
    if (!condition) throw Error(message);
  };
  for (const selector of contract.actions) {
    await check(behavior, `click:${selector}`, async (p) => {
      const target = p.locator(selector);
      assert(
        (await target.isVisible()) && (await target.isEnabled()),
        "Control missing, hidden, or disabled",
      );
      await target.click();
      const state = await p.evaluate(() => window.fixtureState);
      assert(state.clicks === 1, "Click listener effect changed");
      assert(state.submissions === 0, "Action submitted the form unexpectedly");
    });
    for (const key of ["Enter", "Space"]) {
      await check(keyboard, `${key}:${selector}`, async (p) => {
        let reached = false;
        for (let i = 0; i < 30; i += 1) {
          await p.keyboard.press("Tab");
          if (
            await p
              .locator(selector)
              .evaluate((el) => el === document.activeElement)
          ) {
            reached = true;
            break;
          }
        }
        assert(reached, "Control is absent from the Tab order");
        await p.keyboard.press(key);
        const state = await p.evaluate(() => window.fixtureState);
        assert(
          state.clicks === 1,
          `${key} did not activate the click listener exactly once`,
        );
        assert(
          state.submissions === 0,
          `${key} unexpectedly submitted the form`,
        );
      });
    }
  }
  if (contract.submit) {
    await check(behavior, "form:payload", async (p) => {
      for (const [selector, value] of Object.entries(contract.inputs)) {
        assert(
          await p.locator(selector).isVisible(),
          "Input missing or hidden",
        );
        await p.locator(selector).fill(value);
      }
      await p.locator(contract.submit).click();
      const state = await p.evaluate(() => window.fixtureState);
      const expected = {};
      // Names are read from the immutable original, not from candidate HTML.
      const original = await fs.readFile(
        path.join(repository, "fixtures", input.fixture, "contract.json"),
        "utf8",
      );
      const immutable = JSON.parse(original);
      Object.assign(expected, immutable.payload);
      assert(state.submissions === 1, "Form must submit exactly once");
      assert(
        JSON.stringify(
          Object.fromEntries(Object.entries(state.payload || {}).sort()),
        ) ===
          JSON.stringify(Object.fromEntries(Object.entries(expected).sort())),
        "Form payload or field names changed",
      );
      assert(
        state.clicks === 0,
        "Submitting unexpectedly activated another control",
      );
    });
  }
  process.stdout.write(
    JSON.stringify({
      version: 1,
      axe: {
        violations: compact(full.violations),
        incomplete: compact(full.incomplete),
        targeted: compact(targeted.violations),
        targetedIncomplete: compact(targeted.incomplete),
      },
      ...inspection,
      labels,
      behavior,
      keyboard,
      blocked,
      browser: browser.version(),
    }),
  );
  await context.close();
} catch (error) {
  process.stderr.write(String(error.stack));
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  if (browser) await browser.close();
  server.close();
}
