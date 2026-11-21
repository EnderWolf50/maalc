// The window runs the tasks (#815, spec #811 「設定視窗」): Start saves and starts the ticked tasks, Stop asks the runner to
// stop, each posted task shows its state, the live log keeps the last LOG_LINES lines, a run that went wrong says how, the
// device scan fills in the emulator, a run locks the settings it reads, and closing the window during a run hides it in the
// tray. The backend (api.ts) is a fake that keeps what the page asked and hands the test the run's message channel.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import libRs from "../src-tauri/src/lib.rs?raw";
import actionsPy from "../../agent/actions.py?raw";
import luxActionsPy from "../../agent/lux_actions.py?raw";
import sessionPy from "../../runner/session.py?raw";
import cases from "../../tests/runner_cases.json";
import App from "./App";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam, type Settings } from "./model";
import { IDLE, LINK_STATES, LOG_LINES, RESOURCE_STATES, RESULTS, SOURCES, TASK_STATES, reduce, sameAddress, type Device, type Message } from "./runner";
import css from "./index.css?raw";
import { altMove, cssValueOf, dragOnto, queuedTeams } from "./testing";

const zh = TEXT.zh_tw;
// text: the settings file; saved: each text written; starts: each start the page asked for; send: the last run's channel;
// stops: Stop's calls; devices: what a scan finds (an Error: it fails); history: what a page loaded again gets of the run so
// far, with whether it is under way; keepOpen: the close handler; hid: hide-to-tray's calls
const back = vi.hoisted(() => ({
  text: "", saved: [] as string[], starts: [] as { entries: string[]; device: unknown }[],
  send: undefined as ((m: Message) => void) | undefined, startFail: "", stops: 0,
  devices: [] as unknown, scans: 0, history: null as null | { messages: Message[]; active: boolean },
  keepOpen: undefined as undefined | (() => boolean | Promise<boolean>), hid: 0, hideFail: "",
}));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(back.text),
  saveSettings: (text: string) => { back.saved.push(text); back.text = text; return Promise.resolve(); },
  rootDir: () => Promise.resolve("root"),
  startRun: (entries: string[], device: unknown, onMessage: (m: Message) => void) => {
    if (back.startFail) return Promise.reject(new Error(back.startFail));
    back.starts.push({ entries, device });
    back.send = onMessage;
    return Promise.resolve();
  },
  stopRun: () => { back.stops++; return Promise.resolve(true); },
  attachRun: (onMessage: (m: Message) => void) => {
    if (!back.history) return Promise.resolve(false);
    back.send = onMessage;
    const { messages, active } = back.history;
    setTimeout(() => messages.forEach(onMessage)); // a channel's messages come after the call, as the backend's do
    return Promise.resolve(active);
  },
  scanDevices: () => { back.scans++; return back.devices instanceof Error ? Promise.reject(back.devices) : Promise.resolve(back.devices); },
  onCloseRequested: (keepOpen: () => boolean | Promise<boolean>) => { back.keepOpen = keepOpen; return () => {}; },
  hideToTray: () => { back.hid++; return back.hideFail ? Promise.reject(new Error(back.hideFail)) : Promise.resolve(true); },
}));

/** Settings with Claim Mail and Mirror Dungeon ticked, in that order, the other tasks after them unticked (Assemble Modules
 * twice), on the MuMu instance at 16416, and one team. */
function settings() {
  const s = newSettings();
  Object.assign(s, queuedTeams([newTeam(1, "T1")]));
  s.tasks = [{ id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: true },
    ...["ChargeEnkephalin", "AssembleModules", "ExpLuxcavation", "ThreadLuxcavation", "AssembleModules", "ClaimPassMissions"]
      .map((id) => ({ id, enabled: false }))];
  s.emulator = { address: "127.0.0.1:16416", mumu_index: 1, mumu_manager: "C:/MuMu/nx_main/MuMuManager.exe" };
  return s;
}
const fileOf = (s: Settings) => JSON.stringify(s, null, 2) + "\n";
const lastSaved = (): Settings => JSON.parse(back.saved[back.saved.length - 1]);

beforeEach(() => {
  back.text = fileOf(settings());
  back.saved = [];
  back.starts = [];
  back.send = undefined;
  back.startFail = "";
  back.stops = 0;
  back.devices = [];
  back.scans = 0;
  back.history = null;
  back.keepOpen = undefined;
  back.hid = 0;
  back.hideFail = "";
});

/** The window, on the Run tab it opens on, once the settings are read. */
async function open() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("button", { name: zh["runner.start"] });
  return user;
}
const startButton = () => screen.getByRole("button", { name: zh["runner.start"] });
const stopButton = () => screen.getByRole("button", { name: new RegExp(`^(${zh["runner.stop"]}|${zh["runner.stopping"]})$`) });
/** A task's tick; `n` (from 1) the tick of its nth entry, for a task listed more than once. */
const tick = (name: string, n?: number) =>
  screen.getByRole("checkbox", { name: n ? fill(zh["tasks.tick_nth"], { name, n }) : fill(zh["tasks.tick"], { name }) });
/** The task list's rows; the state each one shows of the run ("off": a row the run left out, null: none shown). */
const taskList = () => within(document.querySelector(".task-list")!);
const taskRows = () => taskList().getAllByRole("listitem");
const rowStates = () => taskRows().map((li) => li.querySelector(".task-row")!.getAttribute("data-state"));
// its rows by tag: a role query over 2000 rows takes seconds
const logLines = () => [...screen.getByRole("list", { name: zh["runner.log"] }).querySelectorAll("li")];
const send = (...messages: Message[]) => act(() => { for (const m of messages) back.send!(m); });
const log = (line: string, source: "runner" | "agent" | "console" = "agent"): Message =>
  ({ type: "event", event: "log", t: "10:00:00.000", source, line });
const task = (index: number, entry: string, state: string, reason?: string): Message =>
  ({ type: "event", event: "task", index, entry, state, ...(reason ? { reason } : {}) } as Message);
const exit = (code: number | null, ended: boolean, tail: string[] = []): Message => ({ type: "exit", code, ended, tail });

/** Start from the window and wait until the backend got the start. */
async function started(user: ReturnType<typeof userEvent.setup>) {
  await user.click(startButton());
  await waitFor(() => expect(back.starts).toHaveLength(1));
}

describe("Start and Stop", () => {
  test("Start saves the unsaved edits, then starts the ticked tasks in run order on the file's emulator", async () => {
    const user = await open();
    await user.click(tick("經驗本"));
    await started(user);
    expect(lastSaved().tasks.find((x) => x.id === "ExpLuxcavation")!.enabled).toBe(true);
    expect(back.starts[0].entries).toEqual(["ClaimMail", "MirrorDungeon", "ExpLuxcavation"]);
    expect(back.starts[0].device).toEqual({ address: "127.0.0.1:16416", mumu_index: 1, mumu_manager: "C:/MuMu/nx_main/MuMuManager.exe" });
  });

  test("with nothing unsaved, Start writes nothing", async () => {
    const user = await open();
    await started(user);
    expect(back.saved).toEqual([]);
  });

  test("during a run Start is off and Stop asks the runner to stop; after the stop went it waits, and the exit brings Start back", async () => {
    const user = await open();
    expect(stopButton()).toBeDisabled();
    await started(user);
    expect(startButton()).toBeDisabled();
    expect(stopButton()).toBeEnabled();
    await user.click(stopButton());
    expect(back.stops).toBe(1);
    send({ type: "stopping" });
    expect(stopButton()).toHaveTextContent(zh["runner.stopping"]);
    expect(stopButton()).toBeDisabled();
    send({ type: "event", event: "end", result: "stopped" }, exit(1, true));
    expect(startButton()).toBeEnabled();
    expect(stopButton()).toBeDisabled();
    expect(screen.getByText("已停止")).toBeVisible();
  });

  test("Start is off with no task ticked, and while the settings have problems, saying why", async () => {
    const s = settings();
    s.tasks = s.tasks.map((x) => ({ ...x, enabled: false }));
    back.text = fileOf(s);
    const user = await open();
    expect(startButton()).toBeDisabled();
    expect(screen.getByText(zh["runner.blocked_no_task"])).toBeVisible();
    await user.click(tick("領信"));
    expect(startButton()).toBeEnabled();
    await user.click(screen.getByText(zh["task.MirrorDungeon"]));
    fireEvent.change(screen.getByRole("spinbutton", { name: new RegExp(`^${zh["run.wipe_retries"]}`) }), { target: { value: "-1" } });
    expect(startButton()).toBeDisabled(); // the schema's minimum is 0
    expect(screen.getByText(zh["runner.blocked_problems"])).toBeVisible();
  });

  test("a start the backend refuses says why, and Start comes back", async () => {
    back.startFail = "a run is under way";
    const user = await open();
    await user.click(startButton());
    expect(await screen.findByText(fill(zh["runner.refused"], { error: "Error: a run is under way" }))).toBeVisible();
    expect(startButton()).toBeEnabled();
  });
});

describe("what the run shows", () => {
  /** Settings whose first six rows are ticked, the run's six tasks in this order, and the last two not. */
  const sixTicked = () => {
    const s = settings();
    s.tasks.forEach((x, j) => { x.enabled = j < 6; });
    back.text = fileOf(s);
    return ["ClaimMail", "MirrorDungeon", "ChargeEnkephalin", "AssembleModules", "ExpLuxcavation", "ThreadLuxcavation"];
  };

  test("the k-th ticked row shows the run's k-th task's state, in all six, in words; a row the run left out dims (#877)", async () => {
    const order = sixTicked();
    const user = await open();
    expect(rowStates()).toEqual(Array(8).fill(null)); // no run yet: no states
    await started(user);
    expect(back.starts[0].entries).toEqual(order);
    expect(rowStates()).toEqual([...order.map(() => "pending"), "off", "off"]);
    const states = ["pending", "running", "succeeded", "failed", "stopped", "cancelled"] as const;
    send(...states.map((state, k) => task(k, order[k], state)));
    expect(rowStates()).toEqual([...states, "off", "off"]);
    const rows = taskRows();
    states.forEach((state, k) => expect(within(rows[k]).getByText(zh[`runner.state.${state}`])).toBeVisible());
    for (const row of rows.slice(6)) {
      expect(within(row).queryByText(new RegExp(Object.values(states).map((x) => zh[`runner.state.${x}`]).join("|")))).toBeNull();
      expect(cssValueOf(css, row, "opacity")).toBe("0.55");
    }
    for (const row of rows.slice(0, 6)) expect(cssValueOf(css, row, "opacity")).toBeUndefined();
  });

  test("only the state's words take its colour, the running one's amber; a failed or cancelled row keeps its frame (#877)", async () => {
    const order = sixTicked();
    const user = await open();
    await started(user);
    const states = ["pending", "running", "succeeded", "failed", "stopped", "cancelled"] as const;
    send(...states.map((state, k) => task(k, order[k], state)));
    const rows = taskRows();
    const ink = (k: number) => cssValueOf(css, within(rows[k]).getByText(zh[`runner.state.${states[k]}`]), "color");
    expect(states.map((_, k) => ink(k))).toEqual(["var(--muted)", "var(--accent-ink)", "var(--keep)", "var(--bad)", "var(--accent-ink)", "var(--muted)"]);
    // the frame and the fill of each row as any other's (row 0 is the picked one): no state of the run looks like a wrong
    // setting's red frame, nor like the picked row
    const frame = (li: Element) => ["border-color", "border-style", "background", "outline", "animation"].map((p) => cssValueOf(css, li, p));
    for (const row of rows.slice(2, 6)) expect(frame(row)).toEqual(frame(rows[1]));
    expect(cssValueOf(css, rows[1].querySelector(".task-row")!, "animation")).toBeUndefined();
  });

  test("a failed or cancelled row says why under its name: the runner's reason, else the bot's stop line; tasks named as the list names them, the row's own name in front left out (#877)", async () => {
    const user = await open();
    await user.click(tick("經驗本"));
    await user.click(tick("紐本"));
    await started(user);
    expect(back.starts[0].entries).toEqual(["ClaimMail", "MirrorDungeon", "ExpLuxcavation", "ThreadLuxcavation"]);
    send(log("[maalc] task ClaimMail started"), task(0, "ClaimMail", "running"), log("[maalc] stop: ClaimMail: the mailbox did not open"),
      task(0, "ClaimMail", "failed"), log("[maalc] task MirrorDungeon started"), task(1, "MirrorDungeon", "running"),
      task(1, "MirrorDungeon", "succeeded"), log("[maalc] task ExpLuxcavation started"),
      task(2, "ExpLuxcavation", "failed", "MaintenanceNotice: maintenance before the ThreadLuxcavation task"),
      task(3, "ThreadLuxcavation", "cancelled", "MaintenanceNotice: maintenance"));
    const rows = taskRows();
    const why = (row: HTMLElement) => row.querySelector(".tr-reason")?.textContent ?? null;
    // the ticked rows: 領信, 鏡牢, then 經驗本 and 紐本 after the two unticked ones
    expect([0, 1, 4, 5].map((j) => why(rows[j]))).toEqual(["the mailbox did not open", null,
      "MaintenanceNotice: maintenance before the 紐本 task", "MaintenanceNotice: maintenance"]);
    // in the body's face, not the rows' condensed numerals (ol.reorder .item small): it is a sentence to read
    expect(cssValueOf(css, rows[0].querySelector(".tr-reason")!, "font")).toBe("400 12.5px/1.4 var(--font-ui)");
    // under the name, in the row
    const name = within(rows[0]).getByText("領信");
    expect(name.compareDocumentPosition(within(rows[0]).getByText("the mailbox did not open")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test.each([["a tick"], ["a move"], ["a copy"], ["a remove"], ["an add"], ["a tick undone"], ["a remove undone"]])("after the run the states stay until the list changes: %s clears them for good (#877)", async (edit) => {
    const user = await open();
    await started(user);
    send(task(0, "ClaimMail", "succeeded"), task(1, "MirrorDungeon", "failed"), { type: "event", event: "end", result: "failed" }, exit(0, true));
    const after = ["succeeded", "failed", ...Array(6).fill("off")];
    expect(rowStates()).toEqual(after);
    // another setting, a pick: the list is the run's still
    await user.click(taskList().getByText(zh["task.MirrorDungeon"]));
    await user.selectOptions(screen.getByRole("combobox", { name: new RegExp(`^${zh["run.difficulty"]}`) }), "hard");
    expect(rowStates()).toEqual(after);
    // each edit here leaves the ticked rows the run's tasks, so the list itself changing is what clears them
    const pass = taskRows()[7];
    if (edit === "a tick") await user.click(tick("領通行證任務"));
    if (edit === "a move") await altMove(user, pass, "ArrowUp");
    if (edit === "a copy") await user.click(within(pass).getByRole("button", { name: fill(zh["tasks.copy"], { name: "領通行證任務" }) }));
    if (edit === "a remove") await user.click(within(pass).getByRole("button", { name: fill(zh["tasks.remove"], { name: "領通行證任務" }) }));
    if (edit === "an add") {
      await user.click(taskList().getByRole("button", { name: zh["tasks.add"] }));
      await user.click(screen.getByRole("menuitem", { name: new RegExp(`^${zh["task.ClaimPassMissions"]}`) }));
    }
    // the list as the run's again: the states stay gone
    if (edit === "a tick undone") { await user.click(tick("領通行證任務")); await user.click(tick("領通行證任務")); }
    if (edit === "a remove undone") {
      await user.click(within(pass).getByRole("button", { name: fill(zh["tasks.remove"], { name: "領通行證任務" }) }));
      await user.click(taskList().getByRole("button", { name: zh.undo }));
    }
    expect(rowStates().every((x) => x === null)).toBe(true);
  });

  test("a page loaded again after a run takes the list as it reads it for the run's: its states show, and go at the list's first edit", async () => {
    back.history = { messages: [task(0, "ClaimMail", "pending"), task(1, "MirrorDungeon", "pending"), task(0, "ClaimMail", "succeeded"),
      task(1, "MirrorDungeon", "failed"), { type: "event", event: "end", result: "failed" }, exit(0, true)], active: false };
    const user = await open();
    await waitFor(() => expect(rowStates().slice(0, 2)).toEqual(["succeeded", "failed"]));
    await altMove(user, taskRows()[7], "ArrowUp"); // an unticked row: the ticked ones are the run's still
    expect(rowStates().every((x) => x === null)).toBe(true);
  });

  test("a task with both its entries ticked is posted twice, and each entry shows its own state (#811)", async () => {
    const user = await open();
    await user.click(tick(zh["task.AssembleModules"], 1));
    await user.click(tick(zh["task.AssembleModules"], 2));
    await started(user);
    expect(back.starts[0].entries).toEqual(["ClaimMail", "MirrorDungeon", "AssembleModules", "AssembleModules"]);
    send(task(2, "AssembleModules", "succeeded"), task(3, "AssembleModules", "running"));
    // the list: ClaimMail, MirrorDungeon, ChargeEnkephalin, AssembleModules, ExpLuxcavation, ThreadLuxcavation, AssembleModules, ...
    expect(rowStates()).toEqual(["pending", "pending", "off", "succeeded", "off", "off", "running", "off"]);
  });

  test("the status says what the run is doing: the connection and the resource", async () => {
    const user = await open();
    await started(user);
    expect(screen.getByText(zh["runner.status_starting"])).toBeVisible();
    send({ type: "event", event: "connection", state: "launching", address: "127.0.0.1:16416" });
    expect(screen.getByText(fill(zh["runner.link.launching"], { address: "127.0.0.1:16416" }))).toBeVisible();
    send({ type: "event", event: "connection", state: "connected", address: "127.0.0.1:16416" },
      { type: "event", event: "resource", state: "loaded" });
    expect(screen.getByText(`${fill(zh["runner.link.connected"], { address: "127.0.0.1:16416" })} · ${zh["runner.resource.loaded"]}`)).toBeVisible();
  });

  test("idle, the status line says nothing, its live region there for a screen reader", async () => {
    await open();
    expect(screen.getByRole("status", { name: "" }).closest(".runner-bar")).not.toBeNull();
    expect(document.querySelector(".runner-bar [role=status]")).toHaveTextContent(/^$/);
  });

  test("once a task runs, the status says which of how many, then how long the run has run, outside its live region", async () => {
    const user = await open();
    await started(user);
    // the run's first log line came 65 s ago: the clock counts from it (the runner's clock, HH:MM:SS.mmm)
    const d = new Date(Date.now() - 65_000);
    const t = d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0");
    send({ type: "event", event: "log", t, source: "runner", line: "[run] connected MuMu 127.0.0.1:16416" }, task(0, "ClaimMail", "running"));
    const status = document.querySelector(".runner-bar [role=status]")!;
    expect(status).toHaveTextContent(/^1\/2$/);
    const took = screen.getByText(/^· 01:0[56]$/);
    expect(status.contains(took)).toBe(false);
    expect(took.closest("[role=status], [aria-live]")).toBeNull();
    send(task(0, "ClaimMail", "succeeded"), task(1, "MirrorDungeon", "running"));
    expect(status).toHaveTextContent(/^2\/2$/);
    const now = new Date();
    const end = now.toTimeString().slice(0, 8) + "." + String(now.getMilliseconds()).padStart(3, "0");
    send(task(1, "MirrorDungeon", "failed"), { type: "event", event: "log", t: end, source: "runner", line: "[run] end failed" },
      { type: "event", event: "end", result: "failed" }, exit(0, true));
    // the result as a phrase, its full stop left out before the clock: 「跑完了，有任務沒成功 · 01:05」
    expect(status).toHaveTextContent(/^跑完了，有任務沒成功$/);
    expect(screen.getByText(/^· 01:0[56]$/)).toBeVisible(); // how long it ran, held after the end
  });

  test(`the live log keeps the last ${LOG_LINES} lines; MaaFramework's own output shows only when asked for`, async () => {
    const user = await open();
    await started(user);
    send(...Array.from({ length: LOG_LINES + 5 }, (_, i) => log(`[maalc] line ${i}`)));
    let lines = logLines();
    expect(lines).toHaveLength(LOG_LINES);
    expect(lines[0]).toHaveTextContent("[maalc] line 5");
    expect(lines[LOG_LINES - 1]).toHaveTextContent(`[maalc] line ${LOG_LINES + 4}`);
    send(log("x: 960, y: 540, width: 1920, height: 1080", "console"), { type: "output", line: "Traceback (most recent call last):" });
    lines = logLines();
    expect(lines).toHaveLength(LOG_LINES - 1); // the console line is one of the 2000 kept, and hidden
    expect(lines[lines.length - 1]).toHaveTextContent("Traceback (most recent call last):");
    expect(lines[lines.length - 2]).toHaveTextContent(`[maalc] line ${LOG_LINES + 4}`);
    await user.click(screen.getByLabelText(zh["runner.console"]));
    lines = logLines();
    expect(lines).toHaveLength(LOG_LINES);
    expect(lines[LOG_LINES - 2]).toHaveTextContent("x: 960, y: 540, width: 1920, height: 1080");
    expect(lines[0]).toHaveTextContent("[maalc] line 7"); // two more lines in: the two oldest went
  });

  test("empty, the log says so in one faint line, gone with the first line; how much it keeps is its title's tooltip", async () => {
    const user = await open();
    expect(screen.getByText(zh["runner.log_empty"])).toBeVisible();
    expect(screen.queryByText(fill(zh["runner.log_note"], { n: LOG_LINES }))).toBeNull();
    expect(screen.getByText(zh["runner.log"], { selector: "[title]" })).toHaveAttribute("title", fill(zh["runner.log_note"], { n: LOG_LINES }));
    expect(screen.getByLabelText(zh["runner.console"]).closest("[title]")).toHaveAttribute("title", zh["runner.console_note"]);
    // the frame is named by its title alone, not by the switch on the title's line
    expect(screen.getByRole("group", { name: zh["runner.log"] })).toContainElement(screen.getByRole("list", { name: zh["runner.log"] }));
    await started(user);
    send(log("[maalc] task ClaimMail started"));
    expect(screen.queryByText(zh["runner.log_empty"])).toBeNull();
  });

  test("a line that says a task or the run failed or stopped is in the failed colour; a task it names reads as the list names it", async () => {
    const user = await open();
    await started(user);
    const failed = [
      log("[run] ThreadLuxcavation status=failed t=94s", "runner"), log("[run] ClaimMail status=stopped t=3s", "runner"),
      log("[maalc] stop: Thread Luxcavation: defeated with the 2 retries used up"), log("[run] error stop_timeout: no stop in 60 s", "runner"),
      log("[run] end failed", "runner"), log("[run] end stopped", "runner"),
    ];
    const fine = [log("[run] ClaimMail status=succeeded t=10s", "runner"), log("[maalc] task EXP Luxcavation: 3 battles"), log("[run] end succeeded", "runner")];
    send(...failed, ...fine);
    const lines = logLines();
    const ink = (li: Element) => cssValueOf(css, li.querySelector("span")!, "color");
    expect(lines.slice(0, failed.length).map(ink)).toEqual(failed.map(() => "var(--bad)"));
    for (const li of lines.slice(failed.length)) expect(ink(li)).not.toBe("var(--bad)");
    // the list's names, the line as it came on hover; the run's log file keeps it as it came (the runner writes it)
    expect(lines.map((li) => li.querySelector("span")!.textContent)).toEqual([
      "[run] 紐本 status=failed t=94s", "[run] 領信 status=stopped t=3s", "[maalc] stop: 紐本: defeated with the 2 retries used up",
      "[run] error stop_timeout: no stop in 60 s", "[run] end failed", "[run] end stopped",
      "[run] 領信 status=succeeded t=10s", "[maalc] task 經驗本: 3 battles", "[run] end succeeded",
    ]);
    expect(lines[0]).toHaveAttribute("title", "[run] ThreadLuxcavation status=failed t=94s");
    expect(lines[3]).not.toHaveAttribute("title"); // nothing renamed: nothing to show
  });

  test("the lines the log reds and renames are written as the runner and the bot write them", () => {
    // runner/session.py say, error, finish and the run's end; agent/actions.py log and stop
    for (const line of ['self.out.log("runner", f"[run] {text}")', 'self.say(f"error {kind}: {message}")',
      'self.say(f"end {result}")', "status={self.states[i]}"]) expect(sessionPy).toContain(line);
    for (const line of ['print(f"[maalc] {msg}", flush=True)', 'log(f"stop: {reason}")']) expect(actionsPy).toContain(line);
  });

  test("the bot's English task names, as agent/lux_actions.py writes them, read as the list names them; the game's own label stays", async () => {
    const names = /^LUX = \{"exp": \("([^"]+)",.*"thread": \("([^"]+)",/m.exec(luxActionsPy);
    expect(names).not.toBeNull();
    const [, exp, thread] = names!;
    const user = await open();
    await started(user);
    send(log(`[maalc] stop: ${exp}: no team picked`), log(`[maalc] ${thread}: battle 2 of 3`),
      log(`[maalc] the pass's Clear ${exp} row done`));
    expect(logLines().map((li) => li.querySelector("span")!.textContent)).toEqual([
      "[maalc] stop: 經驗本: no team picked", "[maalc] 紐本: battle 2 of 3", `[maalc] the pass's Clear ${exp} row done`,
    ]);
  });

  test("an ended run's time is from its first log line to its last, also when the page loads it again later", async () => {
    const at = (ago: number) => {
      const d = new Date(Date.now() - ago);
      return d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0");
    };
    const line = (ago: number, text: string): Message => ({ type: "event", event: "log", t: at(ago), source: "runner", line: text });
    back.history = { messages: [line(300_000, "[run] connected MuMu 127.0.0.1:16416"), task(0, "ClaimMail", "succeeded"),
      line(240_000, "[run] end succeeded"), { type: "event", event: "end", result: "succeeded" }, exit(0, true)], active: false };
    await open();
    expect(await screen.findByText(/^· 01:00$/)).toBeVisible(); // 5 min ago to 4 min ago, not to now
  });

  test("a new run starts a new log", async () => {
    const user = await open();
    await started(user);
    send(log("[maalc] the first run"), exit(0, true));
    back.starts = [];
    await started(user);
    expect(logLines()).toHaveLength(0);
  });

  test("a runner that ends before its end event shows its exit code and its last lines; Start comes back", async () => {
    const user = await open();
    await started(user);
    send(log("[run] start ClaimMail,MirrorDungeon"), exit(3, false, ["[run] start ClaimMail,MirrorDungeon", "Fatal Python error: access violation"]));
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(fill(zh["runner.crash"], { code: 3 }));
    expect(alert).toHaveTextContent("Fatal Python error: access violation");
    expect(startButton()).toBeEnabled();
    expect(screen.getByText("執行器意外結束，這次執行失敗")).toBeVisible(); // the run failed (spec #811)
  });

  test("a run that ends without its end event fails the running task and cancels the rest; after a stop, stops it", async () => {
    const user = await open();
    await started(user);
    send(task(0, "ClaimMail", "running"), exit(3, false));
    expect(rowStates().slice(0, 2)).toEqual(["failed", "cancelled"]);
    back.starts = [];
    await started(user);
    send(task(0, "ClaimMail", "succeeded"), task(1, "MirrorDungeon", "running"), { type: "stopping" },
      { type: "killed", reason: "the runner cannot stop MaaFramework" }, exit(1, false));
    expect(rowStates().slice(0, 2)).toEqual(["succeeded", "stopped"]);
  });

  test("the runner's error event, whose own kind names the error, leaves the view as it was", async () => {
    const user = await open();
    await started(user);
    send(log("[run] stop requested"), { type: "event", event: "error", kind: "stop_timeout", message: "MaaFramework did not stop in 60 s" } as Message);
    expect(logLines()).toHaveLength(1);
    expect(stopButton()).toBeEnabled();
  });

  test("a tree the window ended says why, in place of a crash", async () => {
    const user = await open();
    await started(user);
    send({ type: "stopping" }, { type: "killed", reason: "the runner cannot stop MaaFramework" }, exit(1, false));
    expect(screen.getByRole("alert")).toHaveTextContent(fill(zh["runner.killed"], { reason: "the runner cannot stop MaaFramework" }));
    expect(screen.queryByText(fill(zh["runner.crash"], { code: 1 }), { exact: false })).toBeNull();
    expect(screen.getByText("已停止")).toBeVisible();
  });

  test("a page taken up once in the development build's double start shows the run once", async () => {
    back.history = { messages: [log("[maalc] task ClaimMail started")], active: true };
    render(<StrictMode><App /></StrictMode>);
    await screen.findByRole("button", { name: zh["runner.start"] });
    await waitFor(() => expect(logLines()).toHaveLength(1));
    send(log("[maalc] one more"));
    expect(logLines()).toHaveLength(2);
  });

  test("a page loaded again during a run takes up the run so far, Stop on", async () => {
    // the runner posts each task pending at the start (runner/session.py start)
    back.history = { messages: [task(0, "ClaimMail", "pending"), task(1, "MirrorDungeon", "pending"), task(0, "ClaimMail", "running"),
      log("[maalc] task ClaimMail started")], active: true };
    await open();
    await waitFor(() => expect(logLines()).toHaveLength(1));
    expect(rowStates().slice(0, 2)).toEqual(["running", "pending"]);
    expect(stopButton()).toBeEnabled();
    expect(startButton()).toBeDisabled();
  });
});

describe("a narrow window (1180 px wide and less)", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", (media: string) => ({
      media, matches: media.includes("max-width: 1180px"), addEventListener() {}, removeEventListener() {},
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  test("Start, Stop and the status come first, then the list and the options, then the emulator and the log", async () => {
    await open();
    const order = [startButton(), stopButton(), document.querySelector(".runner-bar [role=status]")!, tick("領信"),
      screen.getByRole("group", { name: zh["task.ClaimMail"] }), screen.getByRole("textbox", { name: zh["emu.address"] }),
      screen.getByRole("list", { name: zh["runner.log"] })];
    for (let k = 1; k < order.length; k++) {
      expect(order[k - 1].compareDocumentPosition(order[k]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  test("the line held at the top holds Start, Stop and the status alone: why Start is off shows under it, and scrolls away", async () => {
    const s = settings();
    s.tasks = s.tasks.map((x) => ({ ...x, enabled: false }));
    back.text = fileOf(s);
    await open();
    const why = screen.getByText(zh["runner.blocked_no_task"]);
    expect(startButton().closest(".run-controls")!.contains(why)).toBe(false);
  });

  test("the log is a panel folded until a run starts; its raw-output switch on the title's line ticks and folds nothing", async () => {
    const user = await open();
    const lines = screen.getByRole("list", { name: zh["runner.log"] });
    expect(lines).not.toBeVisible();
    await user.click(screen.getByLabelText(zh["runner.console"]));
    expect(screen.getByLabelText(zh["runner.console"])).toBeChecked();
    expect(lines).not.toBeVisible();
    await user.click(screen.getByText(zh["runner.log"]));
    expect(lines).toBeVisible();
    await user.click(screen.getByText(zh["runner.log"]));
    expect(lines).not.toBeVisible();
    await started(user);
    expect(lines).toBeVisible();
  });
});

const MUMU: Device = { name: "MuMuPlayer-12.0-0", address: "127.0.0.1:16384", adb_path: "C:/MuMu/nx_main/adb.exe",
  mumu: { index: 0, manager: "C:/MuMu/nx_main/MuMuManager.exe", path: "C:/MuMu" } };
const OTHER: Device = { name: "emulator-5554", address: "emulator-5554", adb_path: "C:/adb/adb.exe", mumu: null };

describe("the device scan", () => {
  test("lists the emulators found, MuMu first as the runner sends them; a pick fills in the three fields, which a save writes", async () => {
    back.devices = [MUMU, OTHER];
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["emu.scan"] }));
    const found = await screen.findByRole("combobox", { name: new RegExp(`^${zh["emu.found"]}`) });
    expect([...found.querySelectorAll("option")].map((o) => o.textContent)).toEqual([zh["emu.pick"],
      fill(zh["emu.device_mumu"], { index: 0, address: "127.0.0.1:16384" }), fill(zh["emu.device"], { name: "emulator-5554", address: "emulator-5554" })]);
    await user.selectOptions(found, fill(zh["emu.device_mumu"], { index: 0, address: "127.0.0.1:16384" }));
    expect(screen.getByRole("textbox", { name: zh["emu.address"] })).toHaveValue("127.0.0.1:16384");
    expect(screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] })).toHaveValue(0);
    expect(screen.getByRole("textbox", { name: zh["emu.mumu_manager"] })).toHaveValue("C:/MuMu/nx_main/MuMuManager.exe");
    await user.selectOptions(found, fill(zh["emu.device"], { name: "emulator-5554", address: "emulator-5554" }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(back.saved).toHaveLength(1));
    expect(lastSaved().emulator).toEqual({ address: "emulator-5554", mumu_index: null, mumu_manager: null });
  });

  test("the address the settings hold shows as picked", async () => {
    back.devices = [MUMU, { ...MUMU, address: "127.0.0.1:16416", mumu: { ...MUMU.mumu!, index: 1 } }];
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["emu.scan"] }));
    const found = await screen.findByRole("combobox", { name: new RegExp(`^${zh["emu.found"]}`) });
    expect(found).toHaveDisplayValue(fill(zh["emu.device_mumu"], { index: 1, address: "127.0.0.1:16416" }));
  });

  test("an address alone, as MXU's read-back leaves it, starts on 「選一個…」: a pick of its device fills the instance and MuMuManager (#833)", async () => {
    // readBack.ts takes MXU's adbDeviceAddress only: MXU keeps no MuMu instance or MuMuManager path
    const s = settings();
    s.emulator = { address: "127.0.0.1:16384", mumu_index: null, mumu_manager: null };
    back.text = fileOf(s);
    back.devices = [MUMU, OTHER];
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["emu.scan"] }));
    const found = await screen.findByRole("combobox", { name: new RegExp(`^${zh["emu.found"]}`) });
    expect(found).toHaveDisplayValue(zh["emu.pick"]);
    await user.selectOptions(found, fill(zh["emu.device_mumu"], { index: 0, address: "127.0.0.1:16384" }));
    expect(screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] })).toHaveValue(0);
    expect(screen.getByRole("textbox", { name: zh["emu.mumu_manager"] })).toHaveValue("C:/MuMu/nx_main/MuMuManager.exe");
    expect(found).toHaveDisplayValue(fill(zh["emu.device_mumu"], { index: 0, address: "127.0.0.1:16384" }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(back.saved).toHaveLength(1));
    expect(lastSaved().emulator).toEqual({ address: "127.0.0.1:16384", mumu_index: 0, mumu_manager: "C:/MuMu/nx_main/MuMuManager.exe" });
  });

  test("a field changed by hand after a pick puts the list back on 「選一個…」, so the device can be picked again", async () => {
    back.devices = [MUMU, OTHER];
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["emu.scan"] }));
    const found = await screen.findByRole("combobox", { name: new RegExp(`^${zh["emu.found"]}`) });
    await user.selectOptions(found, fill(zh["emu.device_mumu"], { index: 0, address: "127.0.0.1:16384" }));
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] }), { target: { value: "3" } });
    expect(found).toHaveDisplayValue(zh["emu.pick"]);
    await user.selectOptions(found, fill(zh["emu.device_mumu"], { index: 0, address: "127.0.0.1:16384" }));
    expect(screen.getByRole("spinbutton", { name: zh["emu.mumu_index"] })).toHaveValue(0);
  });

  test("an address the runner takes for the same device shows as picked: localhost is 127.0.0.1 (runner/devices.py)", async () => {
    const s = settings();
    s.emulator.address = "localhost:16416";
    back.text = JSON.stringify(s, null, 2) + "\n";
    back.devices = [MUMU, { ...MUMU, address: "127.0.0.1:16416", mumu: { ...MUMU.mumu!, index: 1 } }];
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["emu.scan"] }));
    const found = await screen.findByRole("combobox", { name: new RegExp(`^${zh["emu.found"]}`) });
    expect(found).toHaveDisplayValue(fill(zh["emu.device_mumu"], { index: 1, address: "127.0.0.1:16416" }));
  });

  test("a scan that finds none, and one that fails, say so", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["emu.scan"] }));
    expect(await screen.findByText(zh["emu.none_found"])).toBeVisible();
    back.devices = new Error("no module named maa");
    await user.click(screen.getByRole("button", { name: zh["emu.scan"] }));
    expect(await screen.findByText(fill(zh["emu.scan_failed"], { error: "Error: no module named maa" }))).toBeVisible();
  });
});

describe("during a run", () => {
  test("the task list, the task options, the global options and the emulator are locked; a task still shows its options", async () => {
    const user = await open();
    // a delete before the run: its Undo would change the list the run reads
    await user.click(taskList().getByRole("button", { name: fill(zh["tasks.remove"], { name: zh["task.ClaimPassMissions"] }) }));
    expect(taskList().getByRole("button", { name: zh.undo })).toBeVisible();
    await started(user);
    // one line says so, where 加入任務 was: the page's one note of the lock
    expect(screen.getAllByText(zh["runner.locked"])).toHaveLength(1);
    expect(taskList().getByText(zh["runner.locked"])).toBeVisible();
    const list = taskList();
    expect(tick("領信")).toBeDisabled();
    // no tick, no copy, no remove, no 加入任務, no Undo
    expect(list.queryAllByRole("button")).toEqual([]);
    for (const row of list.getAllByRole("listitem")) {
      expect(row).toHaveAttribute("draggable", "false");
      for (const box of within(row).getAllByRole("checkbox")) expect(box).toBeDisabled();
    }
    // neither a drag nor Alt with an arrow moves a task (#873)
    const order = () => list.getAllByRole("listitem").map((li) => li.textContent);
    const before = order();
    dragOnto(list.getAllByRole("listitem")[2], list.getAllByRole("listitem")[0]);
    await altMove(user, list.getAllByRole("listitem")[0], "ArrowDown");
    expect(order()).toEqual(before);
    expect(back.starts[0].entries).toEqual(["ClaimMail", "MirrorDungeon"]);
    expect(screen.getByRole("textbox", { name: new RegExp(`^${zh["run.webhook_url"]}`) })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: zh["emu.address"] })).toBeDisabled();
    expect(screen.getByRole("button", { name: zh["emu.scan"] })).toBeDisabled();
    await user.click(list.getByText(zh["task.MirrorDungeon"]));
    expect(screen.getByRole("combobox", { name: new RegExp(`^${zh["run.difficulty"]}`) })).toBeDisabled();
    await user.click(list.getByText(zh["task.ExpLuxcavation"]));
    expect(screen.getByRole("group", { name: "經驗本" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.mode"]}`) })).toBeDisabled();
    send(exit(0, true));
    expect(tick("領信")).toBeEnabled();
    expect(screen.getByRole("textbox", { name: zh["emu.address"] })).toBeEnabled();
    expect(screen.queryByText(zh["runner.locked"])).toBeNull();
    expect(list.getByRole("button", { name: zh["tasks.add"] })).toBeEnabled();
    expect(list.getByRole("button", { name: zh.undo })).toBeVisible(); // back with the run's end
  });

  test("Undo of 放棄變更 is gone during a run: it would bring back edits the run reads", async () => {
    const user = await open();
    await user.click(tick("經驗本"));
    await user.click(screen.getByRole("button", { name: zh.revert }));
    expect(screen.getByRole("button", { name: zh.undo })).toBeVisible();
    await started(user);
    expect(back.saved).toEqual([]);
    expect(screen.queryByRole("button", { name: zh.undo })).toBeNull();
  });

  test("another tab's edit saves as before, the settings the run reads as they were", async () => {
    const user = await open();
    await started(user);
    await user.click(screen.getByRole("tab", { name: zh["tab.teams"] }));
    await user.type(screen.getByRole("textbox", { name: zh.name }), "!");
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(back.saved).toHaveLength(1));
    const saved = lastSaved();
    expect(saved.teams[0].name).toBe("T1!");
    const was = settings();
    expect([saved.tasks, saved.run, saved.emulator]).toEqual([was.tasks, was.run, was.emulator]);
  });

  test("closing the window hides it in the tray; with no run it closes, or asks first with unsaved edits, as before", async () => {
    const user = await open();
    expect(back.keepOpen!()).toBe(false);
    await started(user);
    let kept: boolean | Promise<boolean> = false;
    act(() => { kept = back.keepOpen!(); });
    await expect(kept).resolves.toBe(true);
    expect(back.hid).toBe(1);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    send(exit(0, true));
    expect(back.keepOpen!()).toBe(false);
    expect(back.hid).toBe(1);
  });

  test("a hide that fails keeps the window open and says why: closing it would end the run", async () => {
    back.hideFail = "the app has no icon";
    const user = await open();
    await started(user);
    let kept: boolean | Promise<boolean> = false;
    act(() => { kept = back.keepOpen!(); });
    await expect(kept).resolves.toBe(true);
    expect(await screen.findByText("Error: the app has no icon")).toBeVisible();
  });
});

describe("the runner's events as the page folds them (tests/runner_cases.json, which the runner and the backend run)", () => {
  // the backend relays each event it took under type "event", its "v" dropped (runner.rs Message)
  const valid = cases.events.filter((c) => c.valid).map((c) => {
    const { v: _v, ...event } = c.event as Record<string, unknown>;
    return { type: "event", ...event } as Message & { type: "event" };
  });
  const running = reduce(IDLE, { type: "begin", entries: ["MirrorDungeon", "ExpLuxcavation"] });

  test("each valid event lands where the Run tab shows it", () => {
    for (const m of valid) {
      const v = reduce(running, m);
      if (m.event === "log") expect(v.log[v.log.length - 1]).toMatchObject({ t: m.t, source: m.source, line: m.line });
      else if (m.event === "task") expect(v.tasks[m.index]).toMatchObject({ entry: m.entry, state: m.state });
      else if (m.event === "connection") expect(v.link).toEqual({ state: m.state, address: m.address });
      else if (m.event === "resource") expect(v.resource).toBe(m.state);
      else if (m.event === "end") expect(v.result).toBe(m.result);
      else expect(v).toEqual(running); // ready, devices (a scan's), error (which the runner logs too)
    }
  });

  test("the page knows every value the runner sends: the sources, link states, resource states, task states, results", () => {
    const values = (event: string, field: string) =>
      new Set(cases.events.filter((c) => c.valid && c.event.event === event).map((c) => (c.event as Record<string, unknown>)[field]));
    expect(values("log", "source")).toEqual(new Set(SOURCES));
    expect(values("connection", "state")).toEqual(new Set(LINK_STATES));
    expect(values("resource", "state")).toEqual(new Set(RESOURCE_STATES));
    expect(values("task", "state")).toEqual(new Set(TASK_STATES));
    expect(values("end", "result")).toEqual(new Set(RESULTS));
  });

  test("the run's list: the one it started from; a run taken up takes the settings' first; another list drops it for good (#877)", () => {
    const one = [{ id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: false }];
    const other = [{ id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: true }];
    const begun = reduce(IDLE, { type: "begin", entries: ["ClaimMail"], list: one });
    expect(reduce(begun, { type: "list", list: one })).toBe(begun);
    const edited = reduce(begun, { type: "list", list: other });
    expect([edited.list, edited.unlisted]).toEqual([undefined, true]);
    expect(reduce(edited, { type: "list", list: one }).list).toBeUndefined(); // the list as it was again: still gone
    // a page that took the run up: nothing before the run's tasks are known, then the settings' list as they read
    const taken = reduce(IDLE, task(0, "ClaimMail", "succeeded"));
    expect(reduce(IDLE, { type: "list", list: one })).toBe(IDLE);
    expect(reduce(taken, { type: "list", list: one }).list).toEqual(one);
    // a new run starts on its own list
    expect(reduce(edited, { type: "begin", entries: ["ClaimMail"], list: other })).toMatchObject({ list: other });
    expect(reduce(edited, { type: "begin", entries: ["ClaimMail"], list: other }).unlisted).toBeUndefined();
  });

  describe("a failed task's reason (#877): the runner's, else the bot's last stop line in that task", () => {
    const agent = (line: string): Message => ({ type: "event", event: "log", t: "10:00:00.000", source: "agent", line });
    const fold = (entries: string[], ...messages: Message[]) =>
      messages.reduce(reduce, reduce(IDLE, { type: "begin", entries })).tasks.map((x) => x.reason);
    const begun = (id: string) => agent(`[maalc] task ${id} started`);
    const stopped = (reason: string) => agent(`[maalc] stop: ${reason}`);

    test("the bot's lines as agent/actions.py writes them: a task's start, a stop", () => {
      for (const line of ['log(f"task {argv.node_name} started")', 'log(f"stop: {reason}")']) expect(actionsPy).toContain(line);
    });

    test("a failed task with no reason of the runner's takes the bot's last stop line since the bot started it", () => {
      expect(fold(["ThreadLuxcavation"], begun("ThreadLuxcavation"), task(0, "ThreadLuxcavation", "running"),
        stopped("Thread Luxcavation: battle 2 lost"), stopped("Thread Luxcavation: defeated with the 2 retries used up"),
        task(0, "ThreadLuxcavation", "failed"))).toEqual(["Thread Luxcavation: defeated with the 2 retries used up"]);
    });

    test("the task before's stop line is not the next task's reason", () => {
      expect(fold(["ExpLuxcavation", "ClaimMail"], begun("ExpLuxcavation"), stopped("EXP Luxcavation: no team picked"),
        task(0, "ExpLuxcavation", "failed"), begun("ClaimMail"), task(1, "ClaimMail", "failed")))
        .toEqual(["EXP Luxcavation: no team picked", undefined]);
    });

    test("the next task's start may come before the runner ends the one before (it looks every 0.5 s): each keeps its own", () => {
      expect(fold(["ExpLuxcavation", "ClaimMail"], begun("ExpLuxcavation"), stopped("EXP Luxcavation: no team picked"),
        begun("ClaimMail"), task(0, "ExpLuxcavation", "failed"), task(1, "ClaimMail", "failed")))
        .toEqual(["EXP Luxcavation: no team picked", undefined]);
      // a task listed twice, its entries one after the other: the bot's nth start of it is the run's nth entry of it
      expect(fold(["AssembleModules", "AssembleModules"], begun("AssembleModules"), stopped("no modules to assemble"),
        begun("AssembleModules"), task(0, "AssembleModules", "failed"), task(1, "AssembleModules", "failed")))
        .toEqual(["no modules to assemble", undefined]);
    });

    test("the runner's own reason comes first; a cancelled task, which never ran, takes only the runner's; a stop is no reason", () => {
      expect(fold(["MirrorDungeon", "ClaimMail", "ExpLuxcavation"], begun("MirrorDungeon"), stopped("MaintenanceNotice: maintenance"),
        task(0, "MirrorDungeon", "failed", "MaintenanceNotice: the halt (#870)"), task(1, "ClaimMail", "cancelled"),
        task(2, "ExpLuxcavation", "cancelled", "MaintenanceNotice: maintenance")))
        .toEqual(["MaintenanceNotice: the halt (#870)", undefined, "MaintenanceNotice: maintenance"]);
      expect(fold(["ClaimMail"], begun("ClaimMail"), stopped("x"), task(0, "ClaimMail", "stopped"))).toEqual([undefined]);
    });

    test("only the bot's own lines count: not the runner's, not MaaFramework's output", () => {
      expect(fold(["ClaimMail"], begun("ClaimMail"), log("[maalc] stop: quoted", "runner"), log("[maalc] stop: quoted", "console"),
        task(0, "ClaimMail", "failed"))).toEqual([undefined]);
    });
  });

  test.each(cases.addresses as [string, string, boolean][])("%s and %s are one device: %s, as the runner picks it", (a, b, same) => {
    expect(sameAddress(a, b)).toBe(same);
  });
});

test("the window keeps as many log lines of a run for a page that attaches later as the page shows (lib.rs LOG_KEEP)", () => {
  expect(libRs).toContain(`const LOG_KEEP: usize = ${LOG_LINES};`);
});
