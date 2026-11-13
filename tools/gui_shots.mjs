#!/usr/bin/env node
// Stills of the settings GUI (gui/) rendered in a headless Edge or Chrome, for a design review or a PR's before/after.
//
//   pnpm --dir gui exec vite build; pnpm --dir gui exec vite preview --port 1420   (another shell: the built app)
//   node tools/gui_shots.mjs --out <dir> [--scheme light|dark|both] [--only run,teams] [--lang en_us]
//                            [--settings FILE] [--url URL] [--width 1100 --height 760 --scale 2] [--browser EXE]
//   node tools/gui_shots.mjs --hold teams-full [--port 9222]   (keep that still's page open for a DevTools client)
//
// The page is the real app: in a plain browser gui/src/api.ts reads and writes settings.json in localStorage, which this
// seeds before each still with the `valid` case of tests/settings_cases.json (or --settings), so no file on disk is read
// or written and the header shows "(browser)" for the folder. The built app, not `pnpm dev`: the dev server hands the settings
// validator's Ajv helpers to the browser as CommonJS modules, and loading the `valid` case there fails ("func3 is not a function"). Each still starts from a fresh load, at the window size of
// gui/src-tauri/tauri.conf.json, in the colour scheme asked for. A still named *-full is as tall as its page.
// Writes <out>/<scheme>/<name>.png and prints one line per still. Needs Node 22 or later (global WebSocket), no packages.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const { values: opt } = parseArgs({
  options: {
    out: { type: "string" },
    url: { type: "string", default: "http://localhost:1420/" },
    settings: { type: "string" },
    scheme: { type: "string", default: "light" },
    only: { type: "string" },
    lang: { type: "string" },
    width: { type: "string", default: "1100" },
    height: { type: "string", default: "760" },
    scale: { type: "string", default: "2" },
    browser: { type: "string" },
    hold: { type: "string" },
    port: { type: "string", default: "0" },
  },
});
if (!opt.out && !opt.hold) {
  console.error("--out <dir> or --hold <still> is required");
  process.exit(2);
}
if (opt.hold && opt.port === "0") opt.port = "9222";
const W = Number(opt.width), H = Number(opt.height), SCALE = Number(opt.scale);

// The main tabs by their App.tsx TABS id (the tab's data-tab), so a still does not depend on the language. A build from before
// data-tab is found by the tab's place, which is TABS's order there.
const TAB = { run: 0, teams: 1, gifts: 2, deployment: 3, starlight: 4, themepacks: 5, events: 6, trials: 7, daily: 8 };

/** Each still: page code run after the load (helpers in PAGE_HELPERS as `$`), and which settings it starts from. */
const SHOTS = [
  { name: "run-full", steps: `await $.tab("run", ${TAB.run});` },
  { name: "teams", steps: `await $.tab("teams", ${TAB.teams}); await $.pick("aside li", "Team b");` },
  { name: "teams-full", steps: `await $.tab("teams", ${TAB.teams}); await $.pick("aside li", "Team b"); $.openAll();` },
  { name: "gifts", steps: `await $.tab("gifts", ${TAB.gifts}); await $.select(".gl select", "g1");` },
  { name: "gifts-tip", steps: `await $.tab("gifts", ${TAB.gifts}); await $.select(".gl select", "g1");`, hover: ["[data-gift='9053']", ".gl-tile"] },
  { name: "gifts-buy", steps: `await $.tab("gifts", ${TAB.gifts}); await $.select(".gl select", "g1"); await $.click(".gl-buy");` },
  { name: "deployment", steps: `await $.tab("deployment", ${TAB.deployment});` },
  { name: "starlight", steps: `await $.tab("starlight", ${TAB.starlight});` },
  { name: "themepacks-full", steps: `await $.tab("themepacks", ${TAB.themepacks}); await $.pick("aside li", "Mine");` },
  { name: "events", steps: `await $.tab("events", ${TAB.events});` },
  { name: "trials", steps: `await $.tab("trials", ${TAB.trials});` },
  { name: "daily-full", steps: `await $.tab("daily", ${TAB.daily});` },
  // Save refused: two enabled teams on one TEAMS slot (validate.ts crossCheck), so the banner, the marked tab and field show.
  { name: "save-blocked", settings: "clash", steps: `await $.tab("teams", ${TAB.teams}); await $.click("header button.primary");` },
];

const PAGE_HELPERS = `window.$ = {
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  async settle() { await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); await this.sleep(150); },
  async tab(id, i) {
    const tab = document.querySelector("[data-tab='" + id + "']") ?? document.querySelector("[role=tablist]")?.querySelectorAll("[role=tab]")[i];
    if (!tab) throw new Error("no main tab " + id);
    tab.click(); await this.settle();
  },
  async click(sel) {
    const el = document.querySelector(sel);
    if (!el) throw new Error("nothing matches " + sel);
    el.click(); await this.settle();
  },
  async pick(sel, text) {
    const el = [...document.querySelectorAll(sel)].find((e) => e.textContent.includes(text));
    if (!el) throw new Error("no " + sel + " with " + text);
    el.click(); await this.settle();
  },
  async select(sel, value) {
    const el = document.querySelector(sel);
    if (!el) throw new Error("nothing matches " + sel);
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(el, value);
    el.dispatchEvent(new Event("change", { bubbles: true }));
    await this.settle();
  },
  openAll() { document.querySelectorAll("main details").forEach((d) => { d.open = true; }); },
  async images() {
    const waiting = [...document.images].filter((i) => !i.complete).map((i) => new Promise((r) => { i.onload = i.onerror = r; }));
    await Promise.race([Promise.all(waiting), this.sleep(4000)]);
  },
  /** The page's whole height: the document's, or the scrolling <main>'s when the app scrolls inside it. */
  fullHeight() {
    const main = document.querySelector("main");
    let h = document.documentElement.scrollHeight;
    if (main && main.scrollHeight > main.clientHeight + 1) {
      const r = main.getBoundingClientRect();
      h = Math.max(h, r.top + main.scrollHeight + (innerHeight - r.bottom));
    }
    return Math.ceil(h);
  },
};`;

function settingsText() {
  const base = opt.settings
    ? JSON.parse(readFileSync(opt.settings, "utf8"))
    : JSON.parse(readFileSync(join(REPO, "tests", "settings_cases.json"), "utf8")).valid;
  if (opt.lang) base.language = opt.lang;
  const clash = structuredClone(base);
  if (clash.teams?.length > 1) clash.teams[1].game_team = clash.teams[0].game_team;
  return { valid: JSON.stringify(base, null, 2) + "\n", clash: JSON.stringify(clash, null, 2) + "\n" };
}

function findBrowser() {
  if (opt.browser) return opt.browser;
  const env = process.env;
  const candidates = [
    env["ProgramFiles(x86)"] && join(env["ProgramFiles(x86)"], "Microsoft", "Edge", "Application", "msedge.exe"),
    env.ProgramFiles && join(env.ProgramFiles, "Microsoft", "Edge", "Application", "msedge.exe"),
    env.ProgramFiles && join(env.ProgramFiles, "Google", "Chrome", "Application", "chrome.exe"),
    env.LOCALAPPDATA && join(env.LOCALAPPDATA, "Google", "Chrome", "Application", "chrome.exe"),
  ].filter(Boolean);
  const hit = candidates.find((p) => existsSync(p));
  if (!hit) throw new Error("no Edge or Chrome found; pass --browser <exe>");
  return hit;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** A Chrome DevTools Protocol connection with flat sessions. */
class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.next = 0;
    this.pending = new Map();
    this.waiters = [];
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id !== undefined && this.pending.has(m.id)) {
        const p = this.pending.get(m.id);
        this.pending.delete(m.id);
        if (m.error) p.reject(new Error(`${p.method}: ${m.error.message}`));
        else p.resolve(m.result);
      } else if (m.method) {
        this.waiters = this.waiters.filter((w) => !(w.method === m.method && w.sessionId === m.sessionId && (w.resolve(m.params), true)));
      }
    };
  }
  send(method, params = {}, sessionId) {
    const id = ++this.next;
    this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject, method }));
  }
  once(method, sessionId, ms = 15000) {
    return new Promise((resolve, reject) => {
      const w = { method, sessionId, resolve };
      this.waiters.push(w);
      setTimeout(() => reject(new Error(`timed out waiting for ${method}`)), ms);
    });
  }
}

/** The browser's DevTools WebSocket: from DevToolsActivePort for port 0 (Edge writes no such file for a fixed port), else /json/version. */
async function browserUrl(profile) {
  if (opt.port !== "0") {
    for (let i = 0; i < 100; i++) {
      try {
        return (await (await fetch(`http://127.0.0.1:${opt.port}/json/version`)).json()).webSocketDebuggerUrl;
      } catch { await sleep(100); }
    }
    throw new Error(`nothing answers on DevTools port ${opt.port}`);
  }
  const portFile = join(profile, "DevToolsActivePort");
  let lines = [];
  for (let i = 0; i < 100 && lines.length < 2; i++) {
    if (existsSync(portFile)) lines = readFileSync(portFile, "utf8").trim().split("\n");
    if (lines.length < 2) await sleep(100);
  }
  if (lines.length < 2) throw new Error("the browser wrote no DevToolsActivePort");
  return `ws://127.0.0.1:${lines[0].trim()}${lines[1].trim()}`;
}

async function launch() {
  const profile = mkdtempSync(join(tmpdir(), "gui-shots-"));
  const proc = spawn(findBrowser(), [
    "--headless=new", `--remote-debugging-port=${opt.port}`, `--user-data-dir=${profile}`, "--no-first-run", "--no-default-browser-check",
    "--disable-extensions", "--disable-sync", "--mute-audio", "about:blank",
  ], { stdio: "ignore" });
  const ws = new WebSocket(await browserUrl(profile));
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = () => j(new Error("cannot connect to the browser")); });
  return { cdp: new Cdp(ws), proc, profile, ws };
}

async function evaluate(cdp, session, expression) {
  const r = await cdp.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, session);
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
  return r.result.value;
}

/** A new page brought to the shot's state; the caller closes `targetId`. */
async function open(cdp, scheme, shot, texts) {
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId: s } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  try {
    await cdp.send("Page.enable", {}, s);
    await cdp.send("Runtime.enable", {}, s);
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: SCALE, mobile: false }, s);
    await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: scheme }] }, s);
    const text = texts[shot.settings ?? "valid"];
    await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `localStorage.clear(); localStorage.setItem("settings.json", ${JSON.stringify(text)}); ${PAGE_HELPERS}`,
    }, s);
    const loaded = cdp.once("Page.loadEventFired", s);
    await cdp.send("Page.navigate", { url: opt.url }, s);
    await loaded;
    await evaluate(cdp, s, `(async () => { for (let i = 0; i < 100 && !document.querySelector("[role=tablist]"); i++) await $.sleep(100);
      if (!document.querySelector("[role=tablist]")) throw new Error("the app did not render: " + (document.body?.innerText.slice(0, 300) || "(empty page)"));
      await $.settle(); })()`);
    await evaluate(cdp, s, `(async () => { ${shot.steps} await $.images(); })()`);
    if (shot.hover) {
      // The first selector that matches: the wanted gift of the fixture's list, else any tile.
      const box = await evaluate(cdp, s, `(() => { const el = ${JSON.stringify(shot.hover)}.map((q) => document.querySelector(q)).find(Boolean);
        if (!el) throw new Error("nothing to hover"); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
      await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: box.x, y: box.y }, s);
      await evaluate(cdp, s, `(async () => { await $.sleep(400); await $.images(); })()`);
    }
    if (shot.name.endsWith("-full")) {
      const full = await evaluate(cdp, s, "$.fullHeight()");
      await cdp.send("Emulation.setDeviceMetricsOverride", { width: W, height: Math.max(H, full), deviceScaleFactor: SCALE, mobile: false }, s);
      await evaluate(cdp, s, "(async () => { await $.settle(); await $.images(); await $.settle(); })()");
    }
    return { targetId, s };
  } catch (e) {
    await cdp.send("Target.closeTarget", { targetId }).catch(() => {});
    throw e;
  }
}

async function shoot(cdp, scheme, shot, texts, outDir) {
  const { targetId, s } = await open(cdp, scheme, shot, texts);
  try {
    const { data } = await cdp.send("Page.captureScreenshot", { format: "png" }, s);
    const file = join(outDir, `${shot.name}.png`);
    writeFileSync(file, Buffer.from(data, "base64"));
    return file;
  } finally {
    await cdp.send("Target.closeTarget", { targetId }).catch(() => {});
  }
}

async function main() {
  const schemes = opt.scheme === "both" ? ["light", "dark"] : [opt.scheme];
  const only = opt.only ? new Set(opt.only.split(",")) : null;
  const shots = SHOTS.filter((x) => !only || only.has(x.name) || only.has(x.name.replace(/-full$/, "")));
  const texts = settingsText();
  const { cdp, proc, profile, ws } = await launch();
  let failed = 0;
  try {
    if (opt.hold) {
      // Leave one still's page open for a DevTools client (`impeccable detect --cdp <port>`) until this process is stopped.
      const shot = SHOTS.find((x) => x.name === opt.hold);
      if (!shot) throw new Error(`no still named ${opt.hold}`);
      await open(cdp, schemes[0], shot, texts);
      console.log(`holding ${schemes[0]} ${shot.name} on DevTools port ${opt.port}; stop with Ctrl-C`);
      // Not tied to stdin: a background task has none. The timer keeps the process alive until a signal or a kill.
      const alive = setInterval(() => {}, 1 << 30);
      await new Promise((r) => { process.once("SIGINT", r); process.once("SIGTERM", r); });
      clearInterval(alive);
      return;
    }
    for (const scheme of schemes) {
      const dir = join(resolve(opt.out), scheme);
      mkdirSync(dir, { recursive: true });
      for (const shot of shots) {
        try {
          console.log(`${scheme} ${shot.name}: ${await shoot(cdp, scheme, shot, texts, dir)}`);
        } catch (e) {
          failed++;
          console.log(`${scheme} ${shot.name}: FAILED ${e.message}`);
        }
      }
    }
  } finally {
    await cdp.send("Browser.close").catch(() => {});
    ws.close();
    for (let i = 0; i < 30 && proc.exitCode === null; i++) await sleep(100);
    if (proc.exitCode === null) proc.kill();
    for (let i = 0; i < 10; i++) {
      try { rmSync(profile, { recursive: true, force: true }); break; } catch { await sleep(300); }
    }
  }
  process.exit(failed ? 1 : 0);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
