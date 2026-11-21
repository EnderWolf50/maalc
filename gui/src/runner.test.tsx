// The window runs the tasks (#815, spec #811 「設定視窗」): Start saves and starts the ticked tasks, Stop asks the runner to
// stop, each posted task shows its state, the live log keeps the last LOG_LINES lines, a run that went wrong says how, the
// device scan fills in the emulator, a run locks the settings it reads, and closing the window during a run hides it in the
// tray. The backend (api.ts) is a fake that keeps what the page asked and hands the test the run's message channel.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import libRs from "../src-tauri/src/lib.rs?raw";
import cases from "../../tests/runner_cases.json";
import App from "./App";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam, type Settings } from "./model";
import { IDLE, LINK_STATES, LOG_LINES, RESOURCE_STATES, RESULTS, SOURCES, TASK_STATES, reduce, sameAddress, type Device, type Message } from "./runner";
import { altMove, dragOnto, queuedTeams } from "./testing";

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

/** Settings with Claim Mail and Mirror Dungeon ticked, in that order, on the MuMu instance at 16416, and one team. */
function settings() {
  const s = newSettings();
  Object.assign(s, queuedTeams([newTeam(1, "T1")]));
  s.tasks = [{ id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: true },
    ...s.tasks.filter((x) => x.id !== "ClaimMail" && x.id !== "MirrorDungeon")];
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
const runTasks = () => within(screen.getByRole("list", { name: zh["runner.tasks"] })).getAllByRole("listitem");
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
    expect(screen.getByText(zh["runner.result.stopped"])).toBeVisible();
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
  test("each posted task shows its state, in all six; a task the bot cancelled or stopped in shows why (#870)", async () => {
    const user = await open();
    await started(user);
    expect(runTasks().map((x) => x.textContent)).toEqual([`${zh["task.ClaimMail"]}${zh["runner.state.pending"]}`,
      `${zh["task.MirrorDungeon"]}${zh["runner.state.pending"]}`]);
    const states = ["pending", "running", "succeeded", "failed", "stopped", "cancelled"] as const;
    const why: Partial<Record<string, string>> = { failed: "ClientOutdated: the game client is out of date", cancelled: "maintenance" };
    send(...states.map((state, i) => task(i, "ClaimMail", state, why[state])));
    const rows = runTasks();
    expect(rows).toHaveLength(6);
    states.forEach((state, i) => {
      expect(rows[i]).toHaveAttribute("data-state", state);
      expect(within(rows[i]).getByText(zh[`runner.state.${state}`])).toBeVisible();
    });
    expect(within(rows[3]).getByText(why.failed!)).toBeVisible();
    expect(within(rows[5]).getByText("maintenance")).toBeVisible();
  });

  test("a task with both its entries ticked is posted twice, and each entry shows its own state (#811)", async () => {
    const user = await open();
    await user.click(tick(zh["task.AssembleModules"], 1));
    await user.click(tick(zh["task.AssembleModules"], 2));
    await started(user);
    expect(back.starts[0].entries).toEqual(["ClaimMail", "MirrorDungeon", "AssembleModules", "AssembleModules"]);
    send(task(2, "AssembleModules", "succeeded"), task(3, "AssembleModules", "running"));
    expect(runTasks().map((x) => [x.textContent, x.dataset.state])).toEqual([
      [`${zh["task.ClaimMail"]}${zh["runner.state.pending"]}`, "pending"],
      [`${zh["task.MirrorDungeon"]}${zh["runner.state.pending"]}`, "pending"],
      [`${zh["task.AssembleModules"]}${zh["runner.state.succeeded"]}`, "succeeded"],
      [`${zh["task.AssembleModules"]}${zh["runner.state.running"]}`, "running"],
    ]);
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
    expect(screen.getByText(zh["runner.result.crashed"])).toBeVisible(); // the run failed (spec #811)
  });

  test("a run that ends without its end event fails the running task and cancels the rest; after a stop, stops it", async () => {
    const user = await open();
    await started(user);
    send(task(0, "ClaimMail", "running"), exit(3, false));
    expect(runTasks().map((x) => x.dataset.state)).toEqual(["failed", "cancelled"]);
    back.starts = [];
    await started(user);
    send(task(0, "ClaimMail", "succeeded"), task(1, "MirrorDungeon", "running"), { type: "stopping" },
      { type: "killed", reason: "the runner cannot stop MaaFramework" }, exit(1, false));
    expect(runTasks().map((x) => x.dataset.state)).toEqual(["succeeded", "stopped"]);
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
    expect(screen.getByText(zh["runner.result.stopped"])).toBeVisible();
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
    back.history = { messages: [task(0, "ClaimMail", "running"), log("[maalc] task ClaimMail started")], active: true };
    await open();
    await waitFor(() => expect(logLines()).toHaveLength(1));
    expect(runTasks()[0]).toHaveAttribute("data-state", "running");
    expect(stopButton()).toBeEnabled();
    expect(startButton()).toBeDisabled();
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
    await started(user);
    expect(screen.getByText(zh["runner.locked"])).toBeVisible();
    const list = within(document.querySelector(".task-list")!);
    expect(tick("領信")).toBeDisabled();
    for (const row of list.getAllByRole("listitem")) {
      expect(row).toHaveAttribute("draggable", "false");
      for (const b of within(row).queryAllByRole("button")) expect(b).toBeDisabled();
    }
    // neither a drag nor Alt with an arrow moves a task (#873)
    const order = () => list.getAllByRole("listitem").map((li) => li.textContent);
    const before = order();
    dragOnto(list.getAllByRole("listitem")[2], list.getAllByRole("listitem")[0]);
    await altMove(user, list.getAllByRole("listitem")[0], "ArrowDown");
    expect(order()).toEqual(before);
    expect(screen.getByRole("textbox", { name: new RegExp(`^${zh["run.webhook_url"]}`) })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: zh["emu.address"] })).toBeDisabled();
    expect(screen.getByRole("button", { name: zh["emu.scan"] })).toBeDisabled();
    await user.click(list.getByText(zh["task.MirrorDungeon"]));
    expect(screen.getByRole("combobox", { name: new RegExp(`^${zh["run.difficulty"]}`) })).toBeDisabled();
    await user.click(list.getByText(zh["task.ExpLuxcavation"]));
    expect(screen.getByRole("heading", { name: /經驗本.*ExpLuxcavation/ })).toBeVisible();
    expect(screen.getByRole("combobox", { name: new RegExp(`^${zh["lux.mode"]}`) })).toBeDisabled();
    // no entry added or removed (#811)
    await user.click(list.getAllByText(zh["task.AssembleModules"])[1]);
    expect(screen.getByRole("button", { name: fill(zh["tasks.again"], { name: zh["task.AssembleModules"] }) })).toBeDisabled();
    expect(screen.getByRole("button", { name: zh["tasks.remove"] })).toBeDisabled();
    send(exit(0, true));
    expect(tick("領信")).toBeEnabled();
    expect(screen.getByRole("textbox", { name: zh["emu.address"] })).toBeEnabled();
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

  test.each(cases.addresses as [string, string, boolean][])("%s and %s are one device: %s, as the runner picks it", (a, b, same) => {
    expect(sameAddress(a, b)).toBe(same);
  });
});

test("the window keeps as many log lines of a run for a page that attaches later as the page shows (lib.rs LOG_KEEP)", () => {
  expect(libRs).toContain(`const LOG_KEEP: usize = ${LOG_LINES};`);
});
