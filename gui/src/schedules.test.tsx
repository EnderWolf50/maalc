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
import type { Synced } from "./api";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam, type Settings } from "./model";
import type { Message } from "./runner";
import { queuedTeams } from "./testing";

const zh = TEXT.zh_tw;
const PREFIX = "maalc-1a2b3c4d-";
const back = vi.hoisted(() => ({
  text: "", saved: [] as string[], starts: [] as string[][], send: undefined as ((m: Message) => void) | undefined,
  scheduled: [] as { id: string; opened: boolean }[], more: undefined as (() => void) | undefined,
  logged: [] as string[], syncs: [] as unknown[], syncFail: "", syncErrors: [] as string[], closed: 0,
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
    const done: Synced = { prefix: "maalc-1a2b3c4d-", written: list.map((x) => `maalc-1a2b3c4d-${x.id}`), kept: [], deleted: [], errors: back.syncErrors };
    return Promise.resolve(done);
  },
  closeWindow: () => { back.closed++; return Promise.resolve(); },
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
const secondStart = (id: string) => act(() => { back.scheduled.push({ id, opened: false }); back.more!(); });

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

  test("a task the Task Scheduler refused is named with why", async () => {
    back.syncErrors = [`${PREFIX}s1: Task Scheduler: register: Access is denied.`];
    await open();
    expect(await screen.findByText(zh["sched.sync_errors"])).toBeVisible();
    expect(screen.getByText(`${PREFIX}s1: Task Scheduler: register: Access is denied.`)).toBeVisible();
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
