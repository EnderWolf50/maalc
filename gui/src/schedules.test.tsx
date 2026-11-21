// The scheduled runs (#816, spec #811 「定時執行」): the Run tab's schedules' editor (add, delete, the weekdays, the time, the
// wake switch), the Task Scheduler brought in line at the load and each save, and a scheduled run's start (`--run <id>`)
// with the window closed (it opens, runs the task list and closes), open (it runs there) and with a run under way (skipped,
// and said). The backend (api.ts) is a fake that keeps what the page asked: the saves, the starts, the syncs, the
// schedule.log lines and the window's close; `scheduled` is what take_scheduled hands out, `more` the event a second start
// fires.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import type { Synced, UpdateOutcome } from "./api";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam, type Settings } from "./model";
import type { Message } from "./runner";
import { queuedTeams } from "./testing";

const zh = TEXT.zh_tw;
const PREFIX = "maalc-1a2b3c4d-";
const back = vi.hoisted(() => ({
  text: "", saved: [] as string[], starts: [] as string[][], send: undefined as ((m: Message) => void) | undefined,
  scheduled: [] as { id: string; opened: boolean; update_unfinished?: boolean }[], more: undefined as (() => void) | undefined,
  logged: [] as string[], syncs: [] as unknown[], syncFail: "", syncErrors: [] as string[], closed: 0,
  update: null as UpdateOutcome | null,
}));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(back.text),
  saveSettings: (text: string) => { back.saved.push(text); back.text = text; return Promise.resolve(); },
  rootDir: () => Promise.resolve("root"),
  startRun: (entries: string[], _device: unknown, onMessage: (m: Message) => void) => {
    back.starts.push(entries);
    back.send = onMessage;
    return Promise.resolve();
  },
  attachRun: () => Promise.resolve(false),
  onCloseRequested: () => () => {},
  takeScheduled: () => { const all = back.scheduled; back.scheduled = []; return Promise.resolve(all); },
  onScheduled: (more: () => void) => { back.more = more; return () => {}; },
  logSchedule: (line: string) => { back.logged.push(line); return Promise.resolve(); },
  syncSchedules: (list: Settings["schedules"]) => {
    back.syncs.push(structuredClone(list));
    if (back.syncFail) return Promise.reject(new Error(back.syncFail));
    // a schedule whose id an error names was not written
    const written = list.map((x) => `maalc-1a2b3c4d-${x.id}`).filter((name) => !back.syncErrors.some((e) => e.startsWith(`${name}:`)));
    const done: Synced = { prefix: "maalc-1a2b3c4d-", written, kept: [], deleted: [], errors: back.syncErrors };
    return Promise.resolve(done);
  },
  closeWindow: () => { back.closed++; return Promise.resolve(); },
  lastUpdate: () => Promise.resolve(back.update),
}));

const EVERY_DAY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
/** Settings with Claim Mail and Mirror Dungeon ticked, one team, and `schedules`. */
function settings(schedules: Settings["schedules"] = [{ id: "s1", days: ["mon", "fri"], time: "05:10", wake: true }]) {
  const s = newSettings();
  Object.assign(s, queuedTeams([newTeam(1, "T1")]));
  s.tasks = [{ id: "ClaimMail", enabled: true }, ...s.tasks.filter((x) => x.id !== "ClaimMail")];
  s.tasks.find((x) => x.id === "MirrorDungeon")!.enabled = true;
  s.schedules = schedules;
  return s;
}
const fileOf = (s: Settings) => JSON.stringify(s, null, 2) + "\n";
const lastSaved = (): Settings => JSON.parse(back.saved[back.saved.length - 1]);

beforeEach(() => {
  back.text = fileOf(settings());
  back.saved = [];
  back.starts = [];
  back.send = undefined;
  back.scheduled = [];
  back.more = undefined;
  back.logged = [];
  back.syncs = [];
  back.syncFail = "";
  back.syncErrors = [];
  back.closed = 0;
  back.update = null;
});

/** The window, on the Run tab it opens on, once the settings are read. */
async function open() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("button", { name: zh["runner.start"] });
  return user;
}
const rows = () => within(screen.getByRole("list", { name: zh["sched.title"] })).getAllByRole("listitem");
const day = (row: HTMLElement, name: string) => within(row).getByRole("checkbox", { name });
const timeOf = (row: HTMLElement) => within(row).getByLabelText(zh["sched.time"]) as HTMLInputElement;
const wakeOf = (row: HTMLElement) => within(row).getByRole("checkbox", { name: zh["sched.wake"] });
const save = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole("button", { name: zh.save }));
const logLines = () => [...screen.getByRole("list", { name: zh["runner.log"] }).querySelectorAll("li")].map((li) => li.textContent);
/** schedule.log got a line ending in `text`, after its time. */
const logged = (text: string) => back.logged.some((l) => /^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d /.test(l) && l.endsWith(text));
const send = (...messages: Message[]) => act(() => { for (const m of messages) back.send!(m); });
const exit = (code: number | null, ended: boolean): Message => ({ type: "exit", code, ended, tail: [] });
/** A second start brings a scheduled run: the backend keeps it and fires its event. */
const secondStart = (id: string, update_unfinished = false) =>
  act(() => { back.scheduled.push({ id, opened: false, update_unfinished }); back.more!(); });

describe("the schedules' editor", () => {
  test("a new schedule runs every day at 05:10 and wakes the PC; its days, time and switch change, and a save writes them and their task", async () => {
    back.text = fileOf(settings([]));
    const user = await open();
    expect(screen.getByText(zh["sched.none"])).toBeVisible();
    await user.click(screen.getByRole("button", { name: zh["sched.add"] }));
    const [row] = rows();
    for (const d of ["一", "二", "三", "四", "五", "六", "日"]) expect(day(row, d)).toBeChecked();
    expect(timeOf(row)).toHaveValue("05:10");
    expect(wakeOf(row)).toBeChecked();
    await user.click(day(row, "二"));
    await user.click(day(row, "日"));
    fireEvent.change(timeOf(row), { target: { value: "21:30" } });
    await user.click(wakeOf(row));
    expect(screen.getByText(zh["sched.unsaved"])).toBeVisible();
    await save(user);
    await waitFor(() => expect(back.saved).toHaveLength(1));
    const want = [{ id: "s1", days: ["mon", "wed", "thu", "fri", "sat"], time: "21:30", wake: false }];
    expect(lastSaved().schedules).toEqual(want);
    expect(back.syncs[back.syncs.length - 1]).toEqual(want);
    expect(await screen.findByText(fill(zh["sched.synced"], { n: 1 }))).toBeVisible();
    expect(within(rows()[0]).getByText(fill(zh["sched.task"], { name: `${PREFIX}s1` }))).toBeVisible();
  });

  test("a deleted schedule leaves the file and the Task Scheduler at the save; a new one takes the first id free", async () => {
    back.text = fileOf(settings([{ id: "s1", days: ["mon"], time: "05:10", wake: true }, { id: "s2", days: ["sat"], time: "09:00", wake: false }]));
    const user = await open();
    await user.click(screen.getByRole("button", { name: fill(zh["sched.remove"], { n: 1 }) }));
    expect(rows()).toHaveLength(1);
    expect(timeOf(rows()[0])).toHaveValue("09:00");
    await save(user);
    await waitFor(() => expect(back.saved).toHaveLength(1));
    expect(lastSaved().schedules.map((x) => x.id)).toEqual(["s2"]);
    expect(back.syncs[back.syncs.length - 1]).toEqual([{ id: "s2", days: ["sat"], time: "09:00", wake: false }]);
    await user.click(screen.getByRole("button", { name: zh["sched.add"] }));
    await save(user);
    await waitFor(() => expect(back.saved).toHaveLength(2));
    expect(lastSaved().schedules.map((x) => x.id)).toEqual(["s2", "s1"]);
    expect(lastSaved().schedules[1].days).toEqual(EVERY_DAY);
  });

  test("the last day ticked stays ticked, and a cleared time keeps the one it had: a schedule has both", async () => {
    back.text = fileOf(settings([{ id: "s1", days: ["wed"], time: "05:10", wake: true }]));
    await open();
    const [row] = rows();
    expect(day(row, "三")).toBeChecked();
    expect(day(row, "三")).toBeDisabled();
    expect(day(row, "四")).toBeEnabled();
    fireEvent.change(timeOf(row), { target: { value: "" } });
    expect(timeOf(row)).toHaveValue("05:10");
    expect(screen.queryByText(zh["sched.unsaved"])).toBeNull();
  });

  test("the window's start checks the tasks against the file's schedules, and says when that fails or a task was refused", async () => {
    back.syncFail = "Task Scheduler: connect: Access is denied.";
    await open();
    await waitFor(() => expect(back.syncs).toEqual([[{ id: "s1", days: ["mon", "fri"], time: "05:10", wake: true }]]));
    expect(await screen.findByText(fill(zh["sched.sync_failed"], { error: "Error: Task Scheduler: connect: Access is denied." }))).toBeVisible();
  });

  test("a task the Task Scheduler refused is named with why, and its schedule shows no task name", async () => {
    back.text = fileOf(settings([{ id: "s1", days: ["mon"], time: "05:10", wake: true }, { id: "s2", days: ["tue"], time: "06:00", wake: true }]));
    back.syncErrors = [`${PREFIX}s1: Task Scheduler: register: Access is denied.`];
    await open();
    expect(await screen.findByText(zh["sched.sync_errors"])).toBeVisible();
    expect(screen.getByText(`${PREFIX}s1: Task Scheduler: register: Access is denied.`)).toBeVisible();
    const [s1, s2] = rows();
    expect(within(s1).queryByText(fill(zh["sched.task"], { name: `${PREFIX}s1` }))).toBeNull();
    expect(within(s2).getByText(fill(zh["sched.task"], { name: `${PREFIX}s2` }))).toBeVisible();
  });

  test("schedules the checks refuse (two with one id, by hand) write no task until fixed and saved", async () => {
    back.text = fileOf(settings([{ id: "s1", days: ["mon"], time: "05:10", wake: true }, { id: "s1", days: ["tue"], time: "06:00", wake: true }]));
    await open();
    expect(screen.getByRole("tab", { name: zh["tab.run"] })).toHaveClass("bad");
    await act(async () => {}); // the load's own sync would have gone by now
    expect(back.syncs).toEqual([]);
  });

  test("a run reads no schedule: they stay open to edits during one", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["runner.start"] }));
    await waitFor(() => expect(back.starts).toHaveLength(1));
    expect(screen.getByText(zh["runner.locked"])).toBeVisible();
    expect(day(rows()[0], "二")).toBeEnabled();
    expect(screen.getByRole("button", { name: zh["sched.add"] })).toBeEnabled();
  });
});

describe("a scheduled run's start (--run <id>)", () => {
  test("with the window closed, the schedule opens it, runs the ticked tasks and closes it when the run ends", async () => {
    back.scheduled = [{ id: "s1", opened: true }];
    await open();
    await waitFor(() => expect(back.starts).toEqual([["ClaimMail", "MirrorDungeon"]]));
    await waitFor(() => expect(logged("[schedule] s1: started the task list")).toBe(true));
    expect(logLines().some((l) => l?.endsWith("[schedule] s1: started the task list"))).toBe(true);
    expect(screen.getByText(/排程 s1 開始執行/)).toBeVisible();
    expect(back.closed).toBe(0);
    send({ type: "event", event: "end", result: "succeeded" }, exit(0, true));
    await waitFor(() => expect(back.closed).toBe(1));
    expect(logged("[schedule] s1: the run ended; the window closes")).toBe(true);
  });

  test("a scheduled run brings the live log and Stop into view, once", async () => {
    const seen: Element[] = [];
    const was = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) { seen.push(this); };
    try {
      back.scheduled = [{ id: "s1", opened: true }];
      const user = await open();
      await waitFor(() => expect(seen).toHaveLength(1));
      // the run console: Stop and the live log
      expect(within(seen[0] as HTMLElement).getByRole("button", { name: zh["runner.stop"] })).toBeEnabled();
      expect(within(seen[0] as HTMLElement).getByRole("list", { name: zh["runner.log"] })).toBeInTheDocument();
      await user.click(screen.getByRole("tab", { name: zh["tab.teams"] }));
      await user.click(screen.getByRole("tab", { name: zh["tab.run"] }));
      expect(seen).toHaveLength(1); // back on the Run tab later, the page stays where the user is
    } finally {
      Element.prototype.scrollIntoView = was;
    }
  });

  test("a window the schedule opened that has unsaved edits when the run ends stays open and says why", async () => {
    back.scheduled = [{ id: "s1", opened: true }];
    const user = await open();
    await waitFor(() => expect(back.starts).toHaveLength(1));
    await user.click(screen.getByRole("tab", { name: zh["tab.teams"] }));
    await user.type(screen.getByRole("textbox", { name: zh.name }), "!");
    send(exit(0, true));
    await waitFor(() => expect(logged("[schedule] s1: the run ended; the window stays open: it has unsaved changes")).toBe(true));
    expect(back.closed).toBe(0);
  });

  test("with the window open, the schedule runs there, saving the edits first as Start does, and the window stays open after", async () => {
    const user = await open();
    await user.click(within(document.querySelector(".task-list")!).getByRole("checkbox", { name: fill(zh["tasks.tick"], { name: zh["task.ClaimMail"] }) }));
    secondStart("s1");
    await waitFor(() => expect(back.starts).toEqual([["MirrorDungeon"]]));
    expect(lastSaved().tasks.find((x) => x.id === "ClaimMail")!.enabled).toBe(false);
    expect(await screen.findByText(new RegExp(`排程 s1 開始執行`))).toBeVisible();
    send(exit(0, true));
    await act(async () => {});
    expect(back.closed).toBe(0);
  });

  test("a schedule that comes while the window shows another tab runs on the Run tab", async () => {
    const user = await open();
    await user.click(screen.getByRole("tab", { name: zh["tab.teams"] }));
    secondStart("s1");
    await waitFor(() => expect(back.starts).toHaveLength(1));
    expect(screen.getByRole("tab", { name: zh["tab.run"] })).toHaveAttribute("aria-selected", "true");
  });

  test("during a run a scheduled start is skipped, and the live log, the section and schedule.log say so", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["runner.start"] }));
    await waitFor(() => expect(back.starts).toHaveLength(1));
    secondStart("s1");
    await waitFor(() => expect(logged("[schedule] s1: skipped: a run is under way")).toBe(true));
    expect(back.starts).toHaveLength(1);
    expect(logLines().some((l) => l?.endsWith("[schedule] s1: skipped: a run is under way"))).toBe(true);
    expect(screen.getByText(/排程 s1 略過：已經在執行/)).toBeVisible();
  });

  test("a scheduled start while an update left the folder half replaced is skipped, and its window stays open", async () => {
    // the backend read apply.json and old/ as the start came (update.rs left_unfinished): an apply under way, cut short, or
    // failed with not all of it back
    back.scheduled = [{ id: "s1", opened: true, update_unfinished: true }];
    await open();
    await waitFor(() => expect(logged("[schedule] s1: skipped: an update is under way or left the folder half replaced")).toBe(true));
    expect(back.starts).toEqual([]);
    expect(logLines().some((l) => l?.endsWith("[schedule] s1: skipped: an update is under way or left the folder half replaced"))).toBe(true);
    expect(screen.getByText(/排程 s1 略過：程式更新正在套用，或沒做完、沒能全部還原，資料夾只換了一半/)).toBeVisible();
    expect(back.closed).toBe(0);
  });

  test("the open window goes by the state each scheduled start brings, not by its own start's", async () => {
    // the window opened while an apply had left old/; the user then put the files back: the next start runs
    back.update = { state: "applying", from: "2.0.0", to: "2.1.0", error: null, restored: false };
    await open();
    secondStart("s1", true);
    await waitFor(() => expect(logged("[schedule] s1: skipped: an update is under way or left the folder half replaced")).toBe(true));
    secondStart("s1");
    await waitFor(() => expect(back.starts).toEqual([["ClaimMail", "MirrorDungeon"]]));
  });

  test("a window the schedule opened stays open when the runner ends unexpectedly, and schedule.log has its exit code", async () => {
    back.scheduled = [{ id: "s1", opened: true }];
    await open();
    await waitFor(() => expect(back.starts).toHaveLength(1));
    send(exit(3, false)); // no end event: the runner crashed
    await waitFor(() => expect(logged("[schedule] s1: the runner ended unexpectedly (exit code 3); the window stays open")).toBe(true));
    expect(back.closed).toBe(0);
    expect(screen.getByText(/排程 s1 的執行器意外結束（結束碼 3），視窗留著/)).toBeVisible();
  });

  test("a window the schedule opened closes after a stop that ended the runner's tree, as after any stop", async () => {
    back.scheduled = [{ id: "s1", opened: true }];
    await open();
    await waitFor(() => expect(back.starts).toHaveLength(1));
    send({ type: "stopping" }, { type: "killed", reason: "the runner did not stop" }, exit(null, false));
    await waitFor(() => expect(back.closed).toBe(1));
    expect(logged("[schedule] s1: the run ended; the window closes")).toBe(true);
  });

  test("two schedules at one time: the first runs, the second is skipped", async () => {
    back.text = fileOf(settings([{ id: "s1", days: EVERY_DAY, time: "05:10", wake: true }, { id: "s2", days: ["mon"], time: "05:10", wake: true }]));
    back.scheduled = [{ id: "s1", opened: true }, { id: "s2", opened: false }];
    await open();
    await waitFor(() => expect(logged("[schedule] s2: skipped: a run is under way")).toBe(true));
    expect(back.starts).toHaveLength(1);
    expect(logged("[schedule] s1: started the task list")).toBe(true);
  });

  test("a schedule the settings do not have, or a start Start would refuse, does not run and says why; its window stays open", async () => {
    const s = settings();
    s.tasks = s.tasks.map((x) => ({ ...x, enabled: false }));
    back.text = fileOf(s);
    back.scheduled = [{ id: "s9", opened: true }, { id: "s1", opened: true }];
    await open();
    await waitFor(() => expect(logged("[schedule] s1: not run: no task is ticked")).toBe(true));
    expect(logged("[schedule] s9: not run: the settings have no schedule s9")).toBe(true);
    expect(back.starts).toEqual([]);
    expect(screen.getByText(new RegExp(`排程 s1 沒有執行：${zh["runner.blocked_no_task"]}`))).toBeVisible();
    expect(back.closed).toBe(0);
  });

  test("settings with problems do not run, as Start does not", async () => {
    const s = settings();
    s.run.wipe_retries = -1;
    back.text = fileOf(s);
    back.scheduled = [{ id: "s1", opened: true }];
    await open();
    await waitFor(() => expect(logged("[schedule] s1: not run: the settings have problems")).toBe(true));
    expect(back.starts).toEqual([]);
  });

  test("a window whose settings did not load runs no scheduled start, and schedule.log says why", async () => {
    back.text = "{ half an edit";
    back.scheduled = [{ id: "s1", opened: true }];
    render(<App />);
    await waitFor(() => expect(logged("[schedule] s1: not run: the settings did not load")).toBe(true));
    expect(back.starts).toEqual([]);
  });
});
