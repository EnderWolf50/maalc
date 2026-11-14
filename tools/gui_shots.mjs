#!/usr/bin/env node
// Stills of the settings GUI (gui/) rendered in a headless Edge or Chrome, for a design review or a PR's before/after.
//
//   pnpm --dir gui exec vite build; pnpm --dir gui exec vite preview --port 1420   (another shell: the built app)
//   node tools/gui_shots.mjs --out <dir> [--scheme light|dark|both] [--only run,teams] [--lang en_us]
//                            [--settings FILE] [--url URL] [--width W --height H] [--scale 2] [--browser EXE]
//   node tools/gui_shots.mjs --hold teams-full [--port 9222]   (keep that still's page open for a DevTools client)
// A --hold stopped with a kill, not Ctrl-C, leaves its browser running until the next run of this tool stops it.
//
// The page is the real app: in a plain browser gui/src/api.ts reads and writes settings.json in localStorage, which this
// seeds before each still with the `valid` case of tests/settings_cases.json (or --settings), so no file on disk is read
// or written and the header shows "(browser)" for the folder. The built app, not `pnpm dev`: the dev server hands the settings
// validator's Ajv helpers to the browser as CommonJS modules, and loading the `valid` case there fails ("func3 is not a function"). Each still starts from a fresh load, at the window size of
// gui/src-tauri/tauri.conf.json, in the colour scheme asked for. A still named *-full is as tall as its page.
// Writes <out>/<scheme>/<name>.png and prints one line per still. Needs Node 22 or later (global WebSocket), no packages.
// A refactor's "looks the same": stills of the build before and of the build after, each shot twice, then
// tools/gui_compare.py --before <dir> <dir> --after <dir> <dir>.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
// The settings window as it opens: --width and --height default to it.
const WINDOW = JSON.parse(readFileSync(join(REPO, "gui", "src-tauri", "tauri.conf.json"), "utf8")).app.windows[0];

const { values: opt } = parseArgs({
  options: {
    out: { type: "string" },
    url: { type: "string", default: "http://localhost:1420/" },
    settings: { type: "string" },
    scheme: { type: "string", default: "light" },
    only: { type: "string" },
    lang: { type: "string" },
    width: { type: "string", default: String(WINDOW.width) },
    height: { type: "string", default: String(WINDOW.height) },
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
  // The panels as the page opens them: a closed one's disclosure triangle points right.
  { name: "teams-closed-full", steps: `await $.tab("teams", ${TAB.teams}); await $.pick("aside li", "Team b");` },
  { name: "gifts", steps: `await $.tab("gifts", ${TAB.gifts}); await $.select(".gl select", "g1");` },
  { name: "gifts-tip", steps: `await $.tab("gifts", ${TAB.gifts}); await $.select(".gl select", "g1");`, hover: ["[data-gift='9053']", ".gl-tile"] },
  { name: "gifts-buy", steps: `await $.tab("gifts", ${TAB.gifts}); await $.select(".gl select", "g1"); await $.click(".gl-buy");` },
  { name: "deployment", steps: `await $.tab("deployment", ${TAB.deployment});` },
  { name: "starlight", steps: `await $.tab("starlight", ${TAB.starlight});` },
  { name: "themepacks-full", steps: `await $.tab("themepacks", ${TAB.themepacks}); await $.pick("aside li", "Mine");` },
  // The packs as their cover cards (the view's second chip), the window's height: the covers come from the WebP folder.
  { name: "themepacks-images", steps: `await $.tab("themepacks", ${TAB.themepacks}); await $.pick("aside li", "Mine"); await $.click(".seg.view button:last-child");` },
  { name: "events", steps: `await $.tab("events", ${TAB.events});` },
  { name: "trials", steps: `await $.tab("trials", ${TAB.trials});` },
  { name: "daily-full", steps: `await $.tab("daily", ${TAB.daily});` },
  // Save refused: two enabled teams on one TEAMS slot (validate.ts crossCheck), so the banner, the marked tab and field show.
  { name: "save-blocked", settings: "clash", steps: `await $.tab("teams", ${TAB.teams}); await $.click("header button.primary");` },
  // Unsaved changes: a team renamed and not saved, so the header shows what an edit leaves before Save.
  { name: "unsaved", steps: `await $.tab("teams", ${TAB.teams}); await $.pick("aside li", "Team b"); await $.type(".bar input", "Team b (edited)");` },
  // The prompt F5 opens over unsaved changes (WindowControls.tsx LeavePrompt).
  { name: "leave", steps: `await $.tab("teams", ${TAB.teams}); await $.pick("aside li", "Team b"); await $.type(".bar input", "Team b (edited)");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "F5", bubbles: true })); await $.settle();` },
];

const PAGE_HELPERS = `window.$ = {
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  // The fonts and the transitions too: a still taken while a face of the condensed font swaps in, or while a transition runs,
  // made two runs of one build differ (2026-11-14).
  async frames() { await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); },
  async settle() {
    // every face the stylesheet declares, not only the ones a text has asked for yet: fonts.ready alone left the title's face to
    // swap in after the still now and then
    await Promise.all([...document.fonts].map((f) => f.load().catch(() => {})));
    await this.frames(); await this.sleep(150); await document.fonts.ready;
    await Promise.race([Promise.all(document.getAnimations().map((a) => a.finished.catch(() => {}))), this.sleep(2000)]);
    await this.frames();
  },
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
  /** Set a text field as typing would: React reads the value through the input event. */
  async type(sel, value) {
    const el = document.querySelector(sel);
    if (!el) throw new Error("nothing matches " + sel);
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    await this.settle();
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

/** A run's browser profile in the temp folder, named by the run's pid so a later run can tell whether it is still running. */
const PROFILE = "gui-shots-";
const profileFor = (pid) => mkdtempSync(join(tmpdir(), `${PROFILE}${pid}-`));
const pidOf = (name) => Number(new RegExp(`^${PROFILE}(\\d+)-`).exec(name)?.[1]);

/** Stops the browsers using `profiles` (Windows), then deletes them. The msedge.exe this spawns hands over to the browser and
 * exits, so neither its pid nor a kill of this process's tree reaches the browser, and a run stopped with a kill left it
 * running with its profile (21 crash handlers and 408 profiles in the temp folder by 2026-11-14). */
async function discard(profiles) {
  if (process.platform === "win32" && profiles.length) {
    // The browser quotes the path when it starts its other processes: match the path, not the flag.
    const paths = profiles.map((p) => `'${p.replaceAll("'", "''")}'`).join(",");
    const exe = basename(findBrowser()).replaceAll("'", "''");
    spawnSync("powershell", ["-NoProfile", "-NonInteractive", "-Command",
      `$paths = @(${paths}); Get-CimInstance Win32_Process -Filter "Name='${exe}'" | Where-Object { $c = $_.CommandLine; $c -and ` +
      "@($paths | Where-Object { $c.Contains($_) }).Count } | " +
      "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"], { stdio: "ignore" });
  }
  for (const profile of profiles) {
    for (let i = 0; i < 10; i++) {
      try { rmSync(profile, { recursive: true, force: true }); break; } catch { await sleep(300); }
    }
  }
}

const running = (pid) => { try { process.kill(pid, 0); return true; } catch (e) { return e.code === "EPERM"; } };

/** Discards what runs that ended without cleaning up left: a --hold stopped with a kill is cleaned up by the next run. */
async function sweep() {
  await discard(readdirSync(tmpdir()).filter((name) => pidOf(name) && !running(pidOf(name))).map((name) => join(tmpdir(), name)));
}

async function launch() {
  await sweep();
  const profile = profileFor(process.pid);
  // Drawn without the GPU, with grayscale text at whole-pixel glyph positions: between two runs of one build the GPU's raster
  // gave a gradient or a border a level or two apart and the page's text came out a pixel apart (2026-11-14), so a still
  // compared pixel by pixel (tools/gui_compare.py) differed with nothing changed. The text still does now and then: shoot twice.
  const proc = spawn(findBrowser(), [
    "--headless=new", `--remote-debugging-port=${opt.port}`, `--user-data-dir=${profile}`, "--no-first-run", "--no-default-browser-check",
    "--disable-extensions", "--disable-sync", "--mute-audio", "--disable-gpu", "--disable-lcd-text", "--disable-font-subpixel-positioning", "about:blank",
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
      await evaluate(cdp, s, `(async () => { await $.sleep(400); await $.images(); await $.settle(); })()`);
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
    await discard([profile]);
  }
  process.exit(failed ? 1 : 0);
}

main().catch((e) => { console.error(e.message); process.exit(1); });
