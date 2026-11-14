#!/usr/bin/env node
// Drives the real settings window (the built Tauri app, a WebView2) over DevTools, for what cua-driver's background input
// cannot do: a held press, a drag, keys with modifiers, the light or dark scheme, a page size, an element's box, a still of
// the page. docs/agents/gui-driving.md says when to use cua and when this. Node 22 or later (global WebSocket), no packages.
// The commands and options are in USAGE below (`node tools/gui_devtools.mjs --help`).
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, realpathSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

import { Cdp } from "./cdp.mjs";

const USAGE = `node tools/gui_devtools.mjs <command> ...

  open --root <dir> [--exe EXE] [--settings FILE] [--port N] [--timeout S]
      Copies the built exe (default gui/src-tauri/target/release/maalc-gui.exe) into a throwaway root with demo settings
      (tools/gui_probe.py --prepare-only: the same root, marker and settings), starts it with a DevTools port (a free one
      unless --port) and a WebView2 data folder of its own (<root>/webview2), waits for the page to render, and prints
      {"pid", "hwnd", "port", "root", "holder", "viewport"}. hwnd is cua's window_id. Then it holds, in the
      background: stopping it (Ctrl-C, a background task's stop, taskkill) ends the app with it (libuv puts a child
      that is not detached in a job that is killed with the parent: src/win/process.c) and its WebView2 ends with the
      app (seen on 2026-11-14); the app closing ends it.
  close --root <dir>
      Stops what runs from that root: its maalc-gui.exe and the WebView2 processes on its data folder, whoever started
      them (an app tools/gui_probe.py left there too). open does the same first. A folder that exists without
      gui_probe's marker is refused, so the real install/ is never touched.

  Page commands: each opens a DevTools session on the page at --port N, does its steps and ends.
  eval <expression> | --file F       prints the expression's value as JSON (a Promise is awaited)
  box <target>... [--all]            each target's box, CSS px from the page's top left: top, bottom, left, right,
                                     width, height (--all: every match)
  still <out.png> [--element T] [--pad N] [--mask T]...
                                     a PNG of the page, or of element T with N px around it; each --mask element is
                                     drawn black (the header's "header .path" shows a local path). The page only: the
                                     window with its frame is cua's get_window_state
  scheme <light|dark>                emulates prefers-color-scheme, kept until stopped (or --keep S)
  press <target> [--hold MS] [--move DX,DY] [--steps N] [--button left|right|middle]
                                     presses the mouse at the target, holds it MS (100; 600 with --move), moving by DX,DY
                                     while held, and releases; a drag the page starts is reported and cancelled
  hover <target> [--force]           the pointer on the target (--force: the CSS :hover state only), kept until stopped
                                     (or --keep S)
  key <combo>... [--ime] [--delay MS]
                                     key presses to the focused element: Shift+Tab, Ctrl+S, Alt+F4, F5, Enter, Escape,
                                     PageDown, a, 7 ...; --ime reports the key as an input method's "Process"; prints
                                     what has the focus after
  drag <from> [<to>] [--steps N] [--cancel]
                                     drags <from> onto <to> and drops it, through the page's own drag-and-drop; with no
                                     <to>, or --cancel, the drag stays in the air (over <to>) for --keep S (10), then is
                                     cancelled
  a11y <target>                      the accessibility node: role, name, description, value and its states
  console [--reload] [--seconds S]   the page's console messages and errors for S (5) seconds, one JSON line each

  A target is a point "x,y" (CSS px), a CSS selector (its first match) or "js:<expression>" for an element. An element
  is scrolled into view only when its centre is outside the page; the output names what is under the point ("hit") and
  whether that is something over the target ("covered").
  Session options of every page command: --scheme light|dark and --viewport WxH (the page laid out at that size, drawn
  at the window's top left) for the command's session; --keep S|forever holds the session, and what it emulates, that
  long after the steps; --then <expression> is evaluated once the page has drawn twice and 250 ms passed after the
  steps (a drag in the air is still in the air), and printed.`;

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_EXE = join(REPO, "gui", "src-tauri", "target", "release", "maalc-gui.exe");
const PROBE = join(REPO, "tools", "gui_probe.py");
const MARKER = ".gui-probe-root"; // tools/gui_probe.py MARKER: a root holding it was made by the probe
const APP = "maalc-gui.exe";
const VIEW = "msedgewebview2.exe";
const DATA = "webview2"; // the WebView2 data folder in a root: its own, so the port is not lost to another app's browser

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class UsageError extends Error {
  usage = true;
}
const usage = (message) => { throw new UsageError(message); };

// --- the command line ---------------------------------------------------------------------------------------------

const str = { type: "string" };
const flag = { type: "boolean" };
const SESSION = { port: str, scheme: str, viewport: str, keep: str, then: str };
const COMMANDS = {
  open: { options: { root: str, exe: str, settings: str, port: str, timeout: str } },
  close: { options: { root: str } },
  eval: { page: true, options: { file: str } },
  box: { page: true, options: { all: flag } },
  still: { page: true, options: { element: str, pad: str, mask: { type: "string", multiple: true } } },
  // holds: the command's effect is a state its session holds, so it is kept until stopped unless --keep says otherwise
  scheme: { page: true, holds: true },
  press: { page: true, options: { hold: str, move: str, steps: str, button: str } },
  hover: { page: true, holds: true, options: { force: flag } },
  key: { page: true, options: { ime: flag, delay: str } },
  drag: { page: true, options: { steps: str, cancel: flag } },
  a11y: { page: true },
  console: { page: true, options: { reload: flag, seconds: str } },
};

const number = (text, name, { min = 0, integer = false } = {}) => {
  const n = Number(text);
  if (text === undefined || text === "" || !Number.isFinite(n) || n < min || (integer && !Number.isInteger(n))) {
    usage(`${name} takes a number${integer ? " (whole)" : ""} of at least ${min}, not ${JSON.stringify(text)}`);
  }
  return n;
};
const portNumber = (text) => {
  const port = number(text, "--port", { min: 1, integer: true });
  if (port > 65535) usage(`--port takes a port number, not ${port}`);
  return port;
};
const POINT = /^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/; // "x,y" in CSS px
const pair = (text, name) => {
  const m = POINT.exec(text ?? "");
  if (!m) usage(`${name} takes DX,DY, as 0,40`);
  return { x: Number(m[1]), y: Number(m[2]) };
};
const element = (text, name) => {
  const t = parseTarget(text);
  if (t.kind === "point") usage(`${name} takes an element, not a point`);
  return t;
};

/** The command line as {command, args, options, port, scheme, viewport, keepMs (null: until stopped), then}; throws a
 * UsageError that says what is wrong. */
export function parseCommand(argv) {
  const [command, ...rest] = argv;
  if (!command) usage("no command");
  const spec = COMMANDS[command];
  if (!spec) usage(`unknown command ${command}`);
  let parsed;
  try {
    parsed = parseArgs({ args: rest, options: { ...(spec.page ? SESSION : {}), ...spec.options }, allowPositionals: true, strict: true });
  } catch (e) {
    usage(e.message);
  }
  const { values: options, positionals: args } = parsed;
  const out = { command, args, options };
  if (!spec.page) {
    if (!options.root) usage(`${command} needs --root <dir>`);
    if (options.port !== undefined) out.port = portNumber(options.port);
    if (options.timeout !== undefined) number(options.timeout, "--timeout");
    return out;
  }
  if (options.port === undefined) usage(`${command} needs --port N, the port open printed`);
  out.port = portNumber(options.port);
  if (options.scheme !== undefined && !["light", "dark"].includes(options.scheme)) usage("--scheme takes light or dark");
  out.scheme = options.scheme ?? null;
  if (options.viewport !== undefined) {
    const m = /^(\d+)x(\d+)$/.exec(options.viewport);
    if (!m) usage("--viewport takes WIDTHxHEIGHT, as 800x480");
    out.viewport = { width: Number(m[1]), height: Number(m[2]) };
  } else out.viewport = null;
  out.then = options.then ?? null;

  const targets = (min, max, what) => {
    if (args.length < min) usage(`${command} needs ${what}`);
    if (args.length > max) usage(`${command} takes at most ${max} target${max > 1 ? "s" : ""}, got ${args.length}`);
    return args.map(parseTarget);
  };
  let inAir = false;
  switch (command) {
    case "eval":
      if (!args.length && !options.file) usage("eval needs an expression or --file F");
      break;
    case "box":
      targets(1, Infinity, "a target");
      for (const a of args) element(a, "box");
      break;
    case "still":
      if (args.length !== 1 || !/\.png$/i.test(args[0])) usage("still needs the out .png path");
      if (options.element) element(options.element, "--element");
      for (const m of options.mask ?? []) element(m, "--mask");
      if (options.pad !== undefined) number(options.pad, "--pad");
      break;
    case "scheme":
      if (args.length !== 1 || !["light", "dark"].includes(args[0])) usage("scheme takes light or dark");
      out.scheme = args[0];
      break;
    case "press":
      targets(1, 1, "a target");
      if (options.hold !== undefined) number(options.hold, "--hold");
      if (options.move !== undefined) pair(options.move, "--move");
      if (options.steps !== undefined) number(options.steps, "--steps", { min: 1, integer: true });
      if (options.button !== undefined && !["left", "right", "middle"].includes(options.button)) usage("--button takes left, right or middle");
      break;
    case "hover":
      targets(1, 1, "a target");
      if (options.force) element(args[0], "hover --force");
      break;
    case "a11y":
      targets(1, 1, "a target");
      element(args[0], "a11y");
      break;
    case "key":
      if (!args.length) usage("key needs a key, as Shift+Tab");
      for (const combo of args) keyEvents(combo, options.ime);
      if (options.delay !== undefined) number(options.delay, "--delay");
      break;
    case "drag":
      targets(1, 2, "a target to drag");
      if (options.steps !== undefined) number(options.steps, "--steps", { min: 1, integer: true });
      inAir = args.length === 1 || !!options.cancel;
      break;
    case "console":
      if (args.length) usage("console takes no target");
      if (options.seconds !== undefined) number(options.seconds, "--seconds");
      break;
  }
  if (options.keep === undefined) out.keepMs = inAir ? 10000 : spec.holds ? null : 0;
  else if (options.keep === "forever") {
    if (inAir) usage("a drag in the air is kept for a number of seconds (--keep S), then cancelled; not forever");
    out.keepMs = null;
  } else {
    if (!(Number(options.keep) >= 0)) usage("--keep takes seconds or forever");
    out.keepMs = Number(options.keep) * 1000;
  }
  return out;
}

/** A target: {kind: "point", x, y} for "x,y", {kind: "js", expr} for "js:<expression>", else {kind: "css", selector}. */
export function parseTarget(text) {
  const m = POINT.exec(text);
  if (m) return { kind: "point", x: Number(m[1]), y: Number(m[2]) };
  if (text.startsWith("js:")) return { kind: "js", expr: text.slice(3) };
  return { kind: "css", selector: text };
}

const targetText = (t) => (t.kind === "css" ? t.selector : t.kind === "js" ? `js:${t.expr}` : `${t.x},${t.y}`);

// --- keys ---------------------------------------------------------------------------------------------------------

const MODIFIERS = {
  alt: { key: "Alt", code: "AltLeft", vk: 18, bit: 1 },
  ctrl: { key: "Control", code: "ControlLeft", vk: 17, bit: 2 },
  meta: { key: "Meta", code: "MetaLeft", vk: 91, bit: 4 },
  shift: { key: "Shift", code: "ShiftLeft", vk: 16, bit: 8 },
};
MODIFIERS.control = MODIFIERS.ctrl;
MODIFIERS.win = MODIFIERS.meta;

const NAMED = {
  enter: { key: "Enter", code: "Enter", vk: 13, text: "\r" },
  tab: { key: "Tab", code: "Tab", vk: 9 },
  escape: { key: "Escape", code: "Escape", vk: 27 },
  backspace: { key: "Backspace", code: "Backspace", vk: 8 },
  delete: { key: "Delete", code: "Delete", vk: 46 },
  insert: { key: "Insert", code: "Insert", vk: 45 },
  home: { key: "Home", code: "Home", vk: 36 },
  end: { key: "End", code: "End", vk: 35 },
  pageup: { key: "PageUp", code: "PageUp", vk: 33 },
  pagedown: { key: "PageDown", code: "PageDown", vk: 34 },
  arrowleft: { key: "ArrowLeft", code: "ArrowLeft", vk: 37 },
  arrowup: { key: "ArrowUp", code: "ArrowUp", vk: 38 },
  arrowright: { key: "ArrowRight", code: "ArrowRight", vk: 39 },
  arrowdown: { key: "ArrowDown", code: "ArrowDown", vk: 40 },
  space: { key: " ", code: "Space", vk: 32, text: " " },
  contextmenu: { key: "ContextMenu", code: "ContextMenu", vk: 93 },
  browserrefresh: { key: "BrowserRefresh", code: "BrowserRefresh", vk: 168 },
};
Object.assign(NAMED, { esc: NAMED.escape, del: NAMED.delete, left: NAMED.arrowleft, up: NAMED.arrowup,
  right: NAMED.arrowright, down: NAMED.arrowdown });

function keyOf(name, bits) {
  const shift = bits & MODIFIERS.shift.bit;
  if (/^[a-z]$/i.test(name)) {
    const lower = name.toLowerCase();
    const key = shift ? lower.toUpperCase() : lower;
    return { key, code: `Key${lower.toUpperCase()}`, vk: lower.toUpperCase().charCodeAt(0), text: key, unmodified: lower };
  }
  if (/^[0-9]$/.test(name)) return { key: name, code: `Digit${name}`, vk: 48 + Number(name), text: shift ? undefined : name };
  const f = /^f([1-9]|1\d|2[0-4])$/i.exec(name);
  if (f) return { key: `F${f[1]}`, code: `F${f[1]}`, vk: 111 + Number(f[1]) };
  return NAMED[name.toLowerCase()] ?? null;
}

/** The Input.dispatchKeyEvent params for a key combo ("Shift+Tab"): each modifier down, the key down and up, the modifiers
 * up. A key types its text only with no Ctrl, Alt or Meta; with Alt (and no Ctrl) it is a system key, as Windows sends it.
 * `ime` reports the key as an input method reports it ("Process", 229). */
export function keyEvents(combo, ime = false) {
  const parts = combo.split("+").map((p) => p.trim());
  const name = parts.pop();
  const mods = parts.map((p) => MODIFIERS[p.toLowerCase()] ?? usage(`${combo}: unknown modifier ${p} (Ctrl, Shift, Alt, Meta)`));
  if (MODIFIERS[name.toLowerCase()]) usage(`${combo}: a modifier needs a key after it, as Shift+Tab`);
  const bits = mods.reduce((b, m) => b | m.bit, 0);
  const k = keyOf(name, bits) ?? usage(`${combo}: unknown key ${name}`);
  const plain = !(bits & (MODIFIERS.ctrl.bit | MODIFIERS.alt.bit | MODIFIERS.meta.bit));
  const system = !!(bits & MODIFIERS.alt.bit) && !(bits & MODIFIERS.ctrl.bit);
  const base = (m, key, vk) => ({ key, code: m.code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
  const events = [];
  let held = 0;
  for (const m of mods) {
    held |= m.bit;
    events.push({ type: "rawKeyDown", ...base(m, m.key, m.vk), modifiers: held, location: 1 });
  }
  const main = ime ? base(k, "Process", 229) : base(k, k.key, k.vk);
  const text = !ime && plain && k.text !== undefined ? { text: k.text, unmodifiedText: k.unmodified ?? k.text } : null;
  const sys = system ? { isSystemKey: true } : {};
  events.push({ type: text ? "keyDown" : "rawKeyDown", ...main, modifiers: bits, ...(text ?? {}), ...sys });
  events.push({ type: "keyUp", ...main, modifiers: bits, ...sys });
  for (const m of [...mods].reverse()) {
    held &= ~m.bit;
    events.push({ type: "keyUp", ...base(m, m.key, m.vk), modifiers: held, location: 1 });
  }
  return events;
}

// --- what open started --------------------------------------------------------------------------------------------

export const probeMarker = () => MARKER;

/** "missing", "probe" (made by gui_probe: it holds the marker) or "foreign". */
export function rootState(root) {
  if (!existsSync(root)) return "missing";
  const marker = join(root, MARKER);
  return existsSync(marker) && statSync(marker).isFile() ? "probe" : "foreign";
}

const norm = (p) => p.replaceAll("/", "\\").replace(/\\+$/, "").toLowerCase();

/** Whether `folder` (normalised) occurs in `cmd` as a whole folder: followed by a separator, a quote, a space or the end. */
function usesFolder(cmd, folder) {
  for (let i = cmd.indexOf(folder); i >= 0; i = cmd.indexOf(folder, i + 1)) {
    const after = cmd[i + folder.length];
    if (after === undefined || after === "\\" || after === '"' || after === " ") return true;
  }
  return false;
}

/** The pids, of `processes` ({pid, name, exe, cmd}), that a run on `root` started: the app running from the root's exe,
 * and the WebView2 processes whose command line names the root's data folder. The user's own app (install/) and another
 * root's never match. */
export function startedFrom(processes, root) {
  const r = norm(root);
  const exe = `${r}\\${APP}`;
  const data = `${r}\\${DATA}`;
  return processes.filter((p) => {
    const name = p.name?.toLowerCase();
    if (name === APP) return !!p.exe && norm(p.exe) === exe;
    if (name === VIEW) return !!p.cmd && usesFolder(norm(p.cmd), data);
    return false;
  }).map((p) => p.pid);
}

/** The running maalc-gui.exe and msedgewebview2.exe processes (Windows). */
function listProcesses() {
  if (process.platform !== "win32") return [];
  const r = spawnSync("powershell", ["-NoProfile", "-NonInteractive", "-Command",
    "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " +
    `@(Get-CimInstance Win32_Process -Filter "Name='${APP}' OR Name='${VIEW}'" | ForEach-Object { ` +
    "[pscustomobject]@{ pid = $_.ProcessId; name = $_.Name; exe = $_.ExecutablePath; cmd = $_.CommandLine } }) | ConvertTo-Json -Compress"],
  { encoding: "utf8" });
  if (r.status !== 0) throw new Error(`cannot list processes: ${r.stderr.trim()}`);
  const text = r.stdout.trim();
  if (!text) return [];
  const list = JSON.parse(text);
  return Array.isArray(list) ? list : [list];
}

const taskkill = (pid) => spawnSync("taskkill", ["/T", "/F", "/PID", String(pid)], { stdio: "ignore" });

/** Stops what runs from a probe root (its app with its process tree, then any WebView2 left on its data folder) and waits
 * until none is left, so the root's files are free; returns the pids found. */
async function stopStarted(root) {
  if (rootState(root) !== "probe") return [];
  const found = new Set();
  for (let i = 0; i < 20; i++) {
    const left = startedFrom(listProcesses(), root);
    if (!left.length) return [...found];
    for (const pid of left) {
      found.add(pid);
      taskkill(pid);
    }
    await sleep(300);
  }
  throw new Error(`could not stop what runs from ${root}: ${startedFrom(listProcesses(), root).join(", ")}`);
}

const foreign = (root) => new Error(`${root} exists and has no ${MARKER} marker: tools/gui_probe.py did not make it, so nothing there is started, stopped or deleted`);

async function close(c) {
  const root = resolve(c.options.root);
  const state = rootState(root);
  if (state === "foreign") throw foreign(root);
  print({ stopped: state === "missing" ? [] : await stopStarted(root) });
}

// --- open ---------------------------------------------------------------------------------------------------------

function portFree(port) {
  return new Promise((ok) => {
    const s = createServer();
    s.once("error", () => ok(false));
    s.listen(port, "127.0.0.1", () => s.close(() => ok(true)));
  });
}

function freePort() {
  return new Promise((ok, fail) => {
    const s = createServer();
    s.once("error", fail);
    s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); });
  });
}

/** The app's page among a DevTools port's targets: a page that is not about: or devtools:. */
function pickPage(targets) {
  const pages = targets.filter((t) => t.type === "page");
  return pages.find((t) => !/^(about|devtools):/.test(t.url)) ?? pages[0] ?? null;
}

async function pageAt(port) {
  let targets;
  try {
    targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  } catch {
    throw new Error(`nothing answers on DevTools port ${port}: is open still holding the window?`);
  }
  const page = pickPage(targets);
  if (!page) throw new Error(`no page on DevTools port ${port}`);
  return page;
}

function mainWindow(pid) {
  const r = spawnSync("powershell", ["-NoProfile", "-NonInteractive", "-Command", `(Get-Process -Id ${pid}).MainWindowHandle`], { encoding: "utf8" });
  return Number(r.stdout.trim()) || null;
}

async function open(c) {
  const root = resolve(c.options.root);
  if (rootState(root) === "foreign") throw foreign(root);
  const exe = resolve(c.options.exe ?? DEFAULT_EXE);
  if (!existsSync(exe)) throw new Error(`no exe at ${exe}: build it (pnpm --dir gui tauri build --no-bundle) or pass --exe`);
  const timeout = (c.options.timeout === undefined ? 30 : Number(c.options.timeout)) * 1000;
  const left = await stopStarted(root);
  if (left.length) console.error(`gui_devtools: stopped what an earlier run left on ${root}: ${left.join(", ")}`);
  // The port before the root: laying the root out again deletes what the last run left in it (an edited settings.json).
  const port = c.port ?? await freePort();
  if (!(await portFree(port))) throw new Error(`port ${port} is in use: pass another --port`);
  const settings = c.options.settings ? ["--settings", resolve(c.options.settings)] : [];
  const prep = spawnSync("uv", ["run", "python", PROBE, "--exe", exe, "--root", root, ...settings, "--prepare-only"], { cwd: REPO, encoding: "utf8" });
  if (prep.status !== 0) throw new Error(`gui_probe.py --prepare-only failed: ${(prep.stderr || prep.stdout || prep.error?.message || "").trim()}`);
  const copied = JSON.parse(prep.stdout.trim().split("\n").pop()).exe;

  // The variables WebView2 reads (Microsoft's WebView2 docs, CreateCoreWebView2EnvironmentWithOptions): the port, and a data
  // folder of its own, since a WebView2 that finds another app's browser on its data folder joins it and drops the port.
  const app = spawn(copied, [], { cwd: root, stdio: "ignore", env: { ...process.env,
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${port}`, WEBVIEW2_USER_DATA_FOLDER: join(root, DATA) } });
  let exited = null;
  app.on("exit", (code) => { exited = code ?? "killed"; });
  let shown;
  try {
    const end = Date.now() + timeout;
    let page = null;
    while (!page) {
      if (exited !== null) throw new Error(`the app exited (${exited}) before its page showed`);
      if (Date.now() > end) throw new Error(`no page on DevTools port ${port} within ${timeout / 1000} s`);
      page = await pageAt(port).catch(() => null);
      if (!page) await sleep(200);
    }
    const cdp = await Cdp.connect(page.webSocketDebuggerUrl);
    // Asked again until the page holds a <main>, which App.tsx draws once the settings are read (before, only the title
    // bar): the page may still be navigating to the app, which ends an evaluation under way.
    let viewport = null;
    while (!viewport) {
      if (exited !== null) throw new Error(`the app exited (${exited}) before its page rendered`);
      viewport = await cdp.evaluate(`(() => { const main = document.querySelector("main");
        if (!main) return null;
        if (main.classList.contains("load-error")) return { loadError: main.innerText.slice(0, 300) };
        return { width: innerWidth, height: innerHeight, dpr: devicePixelRatio }; })()`).catch(() => null);
      if (viewport?.loadError) throw new Error(`the app could not read its settings: ${viewport.loadError}`);
      if (viewport) break;
      if (Date.now() > end) {
        const text = await cdp.evaluate(`document.body?.innerText.slice(0, 300) || "(empty page)"`).catch((e) => e.message);
        throw new Error(`the app did not render within ${timeout / 1000} s: ${text}`);
      }
      await sleep(100);
    }
    cdp.ws.close();
    shown = { pid: app.pid, hwnd: mainWindow(app.pid), port, root, holder: process.pid, viewport };
  } catch (e) {
    taskkill(app.pid);
    await stopStarted(root);
    throw e;
  }
  print(shown);
  print({ holding: "until stopped (the app ends with this process), the window closes, or `close --root`" });

  let stopping = false;
  const stop = async (why) => {
    if (stopping) return;
    stopping = true;
    if (exited === null) taskkill(app.pid);
    print({ stopped: why, left: await stopStarted(root) });
    process.exit(0);
  };
  for (const sig of ["SIGINT", "SIGBREAK", "SIGHUP", "SIGTERM"]) process.on(sig, () => stop(sig));
  // The app closed (its window, or a close or open on this root): nothing of ours is left to stop, and a later open on the
  // root may already be starting its own app on the same data folder.
  app.on("exit", () => { if (!stopping) { print({ exited }); process.exit(0); } });
  setInterval(() => {}, 1 << 30);
}

// --- page commands ------------------------------------------------------------------------------------------------

/** Page code that is the element of a css or js target (or, with `all`, the array of every match). */
function elementCode(t, all = false) {
  if (t.kind === "css") return all ? `[...document.querySelectorAll(${JSON.stringify(t.selector)})]` : `document.querySelector(${JSON.stringify(t.selector)})`;
  if (!all) return `(${t.expr})`;
  return `((v) => v == null ? [] : v instanceof Element ? [v] : [...v])(${t.expr})`;
}

const HELPERS = `const round = (v) => Math.round(v * 100) / 100;
  // an element by tag, id, classes and the start of its label or text; not the page's (the header shows a local path)
  const describe = (el) => { if (!el) return null;
    const whole = el === document.body || el === document.documentElement;
    const text = whole ? "" : (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\\s+/g, " ").slice(0, 24);
    return el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + [...el.classList].map((c) => "." + c).join("") + (text ? " " + JSON.stringify(text) : ""); };
  const box = (el) => { const r = el.getBoundingClientRect();
    return { top: round(r.top), bottom: round(r.bottom), left: round(r.left), right: round(r.right), width: round(r.width), height: round(r.height) }; };`;

/** Where a target is: {x, y, hit, covered}. An element off the page is scrolled to the middle first. */
async function pointOf(cdp, t) {
  if (t.kind === "point") {
    return cdp.evaluate(`(() => { ${HELPERS} return { x: ${t.x}, y: ${t.y}, hit: describe(document.elementFromPoint(${t.x}, ${t.y})) }; })()`);
  }
  const at = await cdp.evaluate(`(() => { ${HELPERS}
    const el = ${elementCode(t)};
    if (!el) return null;
    const centre = () => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
    let [x, y] = centre();
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) { el.scrollIntoView({ block: "center", inline: "nearest" }); [x, y] = centre(); }
    const hit = document.elementFromPoint(x, y);
    return { x: round(x), y: round(y), hit: describe(hit), covered: !(hit && el.contains(hit)) };
  })()`);
  if (!at) throw new Error(`nothing matches ${targetText(t)}`);
  return at;
}

/** The objectId of an element target, with DOM enabled for DOM.requestNode and DOM.describeNode. */
async function objectOf(cdp, t) {
  await cdp.send("DOM.enable");
  await cdp.send("DOM.getDocument", { depth: 0 });
  const found = await cdp.evaluate(elementCode(t), undefined, false);
  if (!found.objectId || found.subtype !== "node") throw new Error(`nothing matches ${targetText(t)}`);
  return found.objectId;
}

const frames = (cdp) => cdp.evaluate("new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))");
const mouse = (cdp, type, at, extra = {}) => cdp.send("Input.dispatchMouseEvent", { type, x: at.x, y: at.y, button: "none", buttons: 0, ...extra });
const BUTTONS = { left: 1, right: 2, middle: 4 };

/** Each page command's steps: returns what it prints (or undefined), and pushes onto `undo` what ends a state it leaves. */
const STEPS = {
  async eval(cdp, c) {
    const expression = c.options.file ? readFileSync(c.options.file, "utf8") : c.args.join(" ");
    return { raw: JSON.stringify(await cdp.evaluate(expression)) ?? "undefined" };
  },

  async box(cdp, c) {
    const out = {};
    for (const text of c.args) {
      const t = parseTarget(text);
      out[text] = await cdp.evaluate(`(() => { ${HELPERS}
        const els = ${c.options.all ? elementCode(t, true) : `[${elementCode(t)}].filter(Boolean)`};
        return ${c.options.all ? "els.map(box)" : "els[0] ? box(els[0]) : null"}; })()`);
    }
    return out;
  },

  async still(cdp, c, undo) {
    const out = resolve(c.args[0]);
    for (const text of c.options.mask ?? []) {
      const n = await cdp.evaluate(`(() => { const els = ${elementCode(parseTarget(text), true)};
        for (const el of els) { const r = el.getBoundingClientRect(); const d = document.createElement("div"); d.dataset.guiDevtoolsMask = "";
          Object.assign(d.style, { position: "fixed", left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px",
            background: "#000", zIndex: "2147483647", pointerEvents: "none" }); document.body.append(d); }
        return els.length; })()`);
      if (!n) throw new Error(`--mask ${text} matches nothing: no still taken`);
    }
    if (c.options.mask?.length) undo.push(() => cdp.evaluate(`document.querySelectorAll("[data-gui-devtools-mask]").forEach((d) => d.remove())`));
    let clip;
    if (c.options.element) {
      const t = parseTarget(c.options.element);
      const pad = Number(c.options.pad ?? 0);
      const b = await cdp.evaluate(`(() => { const el = ${elementCode(t)}; if (!el) return null; const r = el.getBoundingClientRect();
        return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height }; })()`);
      if (!b) throw new Error(`--element ${c.options.element} matches nothing`);
      clip = { x: Math.max(0, b.x - pad), y: Math.max(0, b.y - pad), width: b.width + 2 * pad, height: b.height + 2 * pad, scale: 1 };
    }
    await frames(cdp);
    const { data } = await cdp.send("Page.captureScreenshot", { format: "png", ...(clip ? { clip } : {}) });
    const png = Buffer.from(data, "base64");
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, png);
    return { still: out, width: png.readUInt32BE(16), height: png.readUInt32BE(20), dpr: await cdp.evaluate("devicePixelRatio") };
  },

  async scheme(cdp, c) {
    return { scheme: c.scheme, matches: await cdp.evaluate(`matchMedia("(prefers-color-scheme: ${c.scheme})").matches`) };
  },

  async press(cdp, c, undo) {
    const at = await pointOf(cdp, parseTarget(c.args[0]));
    const button = c.options.button ?? "left";
    const buttons = BUTTONS[button];
    const move = c.options.move ? pair(c.options.move, "--move") : null;
    const hold = Number(c.options.hold ?? (move ? 600 : 100));
    let drag = null;
    if (move) {
      cdp.on("Input.dragIntercepted", (p) => { drag = p; });
      await cdp.send("Input.setInterceptDrags", { enabled: true });
      undo.push(() => cdp.send("Input.setInterceptDrags", { enabled: false }));
    }
    let end = at;
    await mouse(cdp, "mouseMoved", at);
    await mouse(cdp, "mousePressed", at, { button, buttons, clickCount: 1 });
    let down = true;
    undo.push(async () => { if (down) await mouse(cdp, "mouseReleased", end, { button, clickCount: 1 }); });
    if (move) {
      const steps = Number(c.options.steps ?? 12);
      for (let i = 1; i <= steps; i++) {
        end = { x: at.x + (move.x * i) / steps, y: at.y + (move.y * i) / steps };
        await mouse(cdp, "mouseMoved", end, { button, buttons });
        await sleep(hold / steps);
      }
      if (drag) await cdp.send("Input.dispatchDragEvent", { type: "dragCancel", x: end.x, y: end.y, data: drag.data });
    } else await sleep(hold);
    await mouse(cdp, "mouseReleased", end, { button, clickCount: 1 });
    down = false;
    return { pressed: at, held: hold, ...(move ? { released: end, dragStarted: !!drag } : {}) };
  },

  async hover(cdp, c, undo) {
    const t = parseTarget(c.args[0]);
    if (c.options.force) {
      const objectId = await objectOf(cdp, t);
      const { nodeId } = await cdp.send("DOM.requestNode", { objectId });
      await cdp.send("CSS.enable");
      await cdp.send("CSS.forcePseudoState", { nodeId, forcedPseudoClasses: ["hover"] });
      undo.push(() => cdp.send("CSS.forcePseudoState", { nodeId, forcedPseudoClasses: [] }));
      return { forced: "hover", on: c.args[0] };
    }
    const at = await pointOf(cdp, t);
    await mouse(cdp, "mouseMoved", at);
    return { hover: at };
  },

  async key(cdp, c) {
    const delay = Number(c.options.delay ?? 50);
    for (const [i, combo] of c.args.entries()) {
      if (i) await sleep(delay);
      for (const e of keyEvents(combo, c.options.ime)) await cdp.send("Input.dispatchKeyEvent", e);
    }
    await frames(cdp);
    return { keys: c.args, focused: await cdp.evaluate(`(() => { ${HELPERS} return describe(document.activeElement); })()`) };
  },

  async drag(cdp, c, undo) {
    const [fromText, toText] = c.args;
    const from = await pointOf(cdp, parseTarget(fromText));
    let drag = null;
    cdp.on("Input.dragIntercepted", (p) => { drag = p; });
    await cdp.send("Input.setInterceptDrags", { enabled: true });
    undo.push(() => cdp.send("Input.setInterceptDrags", { enabled: false }));
    let last = from;
    await mouse(cdp, "mouseMoved", from);
    await mouse(cdp, "mousePressed", from, { button: "left", buttons: 1, clickCount: 1 });
    let down = true;
    undo.push(async () => { if (down) await mouse(cdp, "mouseReleased", last, { button: "left", clickCount: 1 }); });
    // Chromium starts the page's drag from synthetic mouse input once the pointer has moved a few px while pressed; with
    // drags intercepted it reports the drag (Input.dragIntercepted) and the drag events are dispatched here, at the target,
    // so the page's own hit testing picks where it lands.
    const steps = Number(c.options.steps ?? 10);
    for (let i = 1; i <= steps; i++) {
      last = { x: from.x + i * 3, y: from.y + i * 3 };
      await mouse(cdp, "mouseMoved", last, { button: "left", buttons: 1 });
    }
    for (let i = 0; i < 40 && !drag; i++) await sleep(50);
    if (!drag) throw new Error(`the page started no drag at ${fromText}`);
    let over = null;
    let inAir = true;
    undo.push(async () => { if (inAir) await cdp.send("Input.dispatchDragEvent", { type: "dragCancel", x: last.x, y: last.y, data: drag.data }); });
    if (toText) {
      over = await pointOf(cdp, parseTarget(toText)); // after the drag began: the page may have moved the target since
      for (const type of ["dragEnter", "dragOver"]) {
        await cdp.send("Input.dispatchDragEvent", { type, x: over.x, y: over.y, data: drag.data });
        await sleep(120);
      }
      last = over;
      if (!c.options.cancel) {
        await cdp.send("Input.dispatchDragEvent", { type: "drop", x: over.x, y: over.y, data: drag.data });
        inAir = false;
        await sleep(120);
        await mouse(cdp, "mouseReleased", over, { button: "left", clickCount: 1 });
        down = false;
      }
    }
    return { from, ...(over ? { to: over } : {}), dropped: !inAir };
  },

  async a11y(cdp, c) {
    const objectId = await objectOf(cdp, parseTarget(c.args[0]));
    const { node } = await cdp.send("DOM.describeNode", { objectId });
    const { nodes } = await cdp.send("Accessibility.getPartialAXTree", { backendNodeId: node.backendNodeId, fetchRelatives: false });
    const n = nodes.find((x) => x.backendDOMNodeId === node.backendNodeId) ?? nodes[0];
    const out = { role: n.role?.value ?? null, name: n.name?.value ?? null, description: n.description?.value ?? null,
      value: n.value?.value ?? null, ignored: !!n.ignored };
    for (const p of n.properties ?? []) out[p.name] = p.value?.value ?? null;
    return out;
  },

  async console(cdp, c) {
    const text = (args) => args.map((a) => (a.value !== undefined ? String(a.value) : a.description ?? a.type)).join(" ");
    cdp.on("Runtime.consoleAPICalled", (p) => print({ console: p.type, text: text(p.args) }));
    cdp.on("Runtime.exceptionThrown", (p) => print({ exception: p.exceptionDetails.exception?.description ?? p.exceptionDetails.text,
      url: p.exceptionDetails.url ?? null, line: p.exceptionDetails.lineNumber ?? null }));
    cdp.on("Log.entryAdded", (p) => print({ log: p.entry.level, source: p.entry.source, text: p.entry.text, url: p.entry.url ?? null }));
    await cdp.send("Runtime.enable");
    await cdp.send("Log.enable");
    if (c.options.reload) await cdp.send("Page.reload");
    await sleep(Number(c.options.seconds ?? 5) * 1000);
    return undefined;
  },
};

async function pageCommand(c) {
  const page = await pageAt(c.port);
  const cdp = await Cdp.connect(page.webSocketDebuggerUrl);
  const undo = [];
  let finished = false;
  const finish = async () => {
    if (finished) return;
    finished = true;
    for (const f of undo.reverse()) await f().catch(() => {});
    cdp.ws.close();
  };
  for (const sig of ["SIGINT", "SIGBREAK", "SIGHUP"]) process.on(sig, async () => { await finish(); process.exit(130); });
  try {
    if (c.scheme) await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: c.scheme }] });
    if (c.viewport) await cdp.send("Emulation.setDeviceMetricsOverride", { ...c.viewport, deviceScaleFactor: 0, mobile: false });
    if (c.scheme || c.viewport) await frames(cdp);
    const out = await STEPS[c.command](cdp, c, undo);
    if (out?.raw !== undefined) console.log(out.raw);
    else if (out !== undefined) print(out);
    if (c.then) {
      await frames(cdp);
      await sleep(250);
      print({ then: await cdp.evaluate(c.then) });
    }
    if (c.keepMs !== 0) {
      print({ keeping: c.keepMs === null ? "until stopped" : c.keepMs / 1000 });
      await (c.keepMs === null ? new Promise(() => setInterval(() => {}, 1 << 30)) : sleep(c.keepMs));
    }
  } finally {
    await finish();
  }
}

// --- main ---------------------------------------------------------------------------------------------------------

function print(value) {
  console.log(JSON.stringify(value));
}

async function main(argv) {
  if (["--help", "-h", "help"].includes(argv[0])) {
    console.log(USAGE);
    return 0;
  }
  let c;
  try {
    c = parseCommand(argv);
  } catch (e) {
    if (!e.usage) throw e;
    console.error(`gui_devtools: ${e.message}\n\n${USAGE}`);
    return 2;
  }
  if (c.command === "open") await open(c);
  else if (c.command === "close") await close(c);
  else await pageCommand(c);
  return 0;
}

const direct = process.argv[1] && pathToFileURL(realpathSync(process.argv[1])).href === import.meta.url;
if (direct) {
  main(process.argv.slice(2)).then((code) => { if (code !== undefined) process.exitCode = code; },
    (e) => { console.error(`gui_devtools: ${e.message}`); process.exit(e.usage ? 2 : 1); });
}
