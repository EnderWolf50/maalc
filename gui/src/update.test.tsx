// The window's self-update (#817, spec #811 「自動更新」): a newer release shows in the header, the click downloads it with its
// progress, a sha256 that differs or a download that fails says why and applies nothing, the apply saves first and waits for
// no run, and the window says how the last apply went. The backend (api.ts) is a fake that keeps what the page asked and
// hands the test the download's progress channel and the run's message channel.
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import type { Release, UpdateOutcome, UpdateProgress } from "./api";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam } from "./model";
import type { Message } from "./runner";
import { queuedTeams } from "./testing";

const zh = TEXT.zh_tw;
const RELEASE: Release = {
  tag: "v1.1.0", version: "1.1.0", page: "https://github.com/x/releases/tag/v1.1.0", zip: "https://github.com/x/maalc-v1.1.0.zip",
  size: 1000, sha256: "a".repeat(64),
};
// release: what the check finds; checks: its calls; outcome: how the last apply went; progress: the download's channel;
// download: settles the download (an Error: it fails); applies: the apply's calls; applyFail: the apply's error; saved: each
// text written; send: the run's channel
const back = vi.hoisted(() => ({
  text: "", release: null as Release | null, checks: 0, outcome: null as UpdateOutcome | null,
  progress: undefined as ((p: UpdateProgress) => void) | undefined, download: undefined as ((e?: Error) => void) | undefined,
  downloads: 0, applies: 0, applyFail: "", saved: [] as string[], send: undefined as ((m: Message) => void) | undefined,
}));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(back.text),
  saveSettings: (text: string) => { back.saved.push(text); back.text = text; return Promise.resolve(); },
  rootDir: () => Promise.resolve("root"),
  checkUpdate: () => { back.checks++; return Promise.resolve({ current: "1.0.0", release: back.release }); },
  lastUpdate: () => Promise.resolve(back.outcome),
  downloadUpdate: (onProgress: (p: UpdateProgress) => void) => {
    back.downloads++;
    back.progress = onProgress;
    return new Promise<void>((resolve, reject) => { back.download = (e) => (e ? reject(e) : resolve()); });
  },
  applyUpdate: () => { back.applies++; return back.applyFail ? Promise.reject(new Error(back.applyFail)) : Promise.resolve(); },
  startRun: (_entries: string[], _device: unknown, onMessage: (m: Message) => void) => { back.send = onMessage; return Promise.resolve(); },
}));

function settingsText() {
  const s = newSettings();
  Object.assign(s, queuedTeams([newTeam(1, "T1")]));
  s.tasks = s.tasks.map((x) => ({ ...x, enabled: x.id === "ClaimMail" }));
  return JSON.stringify(s, null, 2) + "\n";
}

beforeEach(() => {
  Object.assign(back, {
    text: settingsText(), release: RELEASE, checks: 0, outcome: null, progress: undefined, download: undefined, downloads: 0,
    applies: 0, applyFail: "", saved: [], send: undefined,
  });
});

async function open() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("button", { name: zh["runner.start"] });
  return user;
}
const v = { version: "1.1.0", current: "1.0.0" };
const progress = (...p: UpdateProgress[]) => act(() => { for (const x of p) back.progress!(x); });
const finish = (e?: Error) => act(async () => { back.download!(e); });
/** The notice above the tabs. */
const notice = () => screen.getByRole("alert", { name: zh["update.notice"] });

describe("the header's notice", () => {
  test("a newer release shows in the header with this build's version; the check is asked once", async () => {
    await open();
    expect(await screen.findByRole("button", { name: fill(zh["update.available"], v) })).toHaveAttribute("title", fill(zh["update.title"], v));
    expect(back.checks).toBe(1);
  });

  test("with no newer release (or a check that failed) the header says nothing", async () => {
    back.release = null;
    await open();
    await waitFor(() => expect(back.checks).toBe(1));
    expect(screen.queryByText(/v1\.1\.0/)).toBeNull();
    expect(document.querySelector("header .update")).toBeNull();
  });
});

describe("the update", () => {
  test("the click downloads with its progress, checks the sha256, unpacks, then applies", async () => {
    const user = await open();
    await user.click(await screen.findByRole("button", { name: fill(zh["update.available"], v) }));
    expect(back.downloads).toBe(1);
    progress({ step: "download", received: 420, total: 1000 });
    const bar = screen.getByRole("progressbar", { name: fill(zh["update.label"], v) });
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(bar).toHaveTextContent(fill(zh["update.downloading"], { pct: 42 }));
    progress({ step: "download", received: 1000, total: 1000 });
    expect(bar).toHaveTextContent(fill(zh["update.downloading"], { pct: 100 }));
    progress({ step: "verify" });
    expect(screen.getByText(zh["update.verify"]).closest("[role=status]")).toHaveClass("update");
    progress({ step: "extract" });
    expect(screen.getByText(zh["update.extract"]).closest("[role=status]")).toHaveClass("update");
    expect(back.applies).toBe(0);
    await finish();
    expect(back.applies).toBe(1);
    expect(back.saved).toEqual([]); // nothing unsaved: nothing written
    expect(screen.getByText(zh["update.applying"])).toBeVisible();
  });

  test("a download whose size is not known counts its megabytes", async () => {
    const user = await open();
    await user.click(await screen.findByRole("button", { name: fill(zh["update.available"], v) }));
    progress({ step: "download", received: 5 * 2 ** 20, total: 0 });
    expect(screen.getByRole("progressbar")).toHaveTextContent(fill(zh["update.downloading_mb"], { mb: 5 }));
  });

  test("a sha256 that differs applies nothing and says so with both hashes; the header offers another try", async () => {
    const user = await open();
    await user.click(await screen.findByRole("button", { name: fill(zh["update.available"], v) }));
    const why = `sha256 mismatch: GitHub gives ${"a".repeat(64)} for ${RELEASE.zip}, the download is ${"b".repeat(64)}`;
    await finish(new Error(why));
    expect(back.applies).toBe(0);
    expect(notice()).toHaveTextContent(fill(zh["update.mismatch"], v));
    expect(notice()).toHaveTextContent("b".repeat(64));
    const retry = screen.getByRole("button", { name: zh["update.retry"] });
    await user.click(retry);
    expect(back.downloads).toBe(2);
    expect(screen.queryByRole("alert", { name: zh["update.notice"] })).toBeNull(); // a new try clears what the last one said
  });

  test("a download that fails says why and applies nothing; the notice goes when dismissed", async () => {
    const user = await open();
    await user.click(await screen.findByRole("button", { name: fill(zh["update.available"], v) }));
    await finish(new Error("https://github.com/x/maalc-v1.1.0.zip: timed out"));
    expect(back.applies).toBe(0);
    expect(notice()).toHaveTextContent(fill(zh["update.download_failed"], { ...v, error: "Error: https://github.com/x/maalc-v1.1.0.zip: timed out" }));
    await user.click(screen.getByRole("button", { name: zh["update.dismiss"] }));
    expect(screen.queryByRole("alert", { name: zh["update.notice"] })).toBeNull();
    expect(screen.getByRole("button", { name: zh["update.retry"] })).toBeVisible();
  });

  test("an apply that cannot start says why", async () => {
    back.applyFail = "C:\\maalc\\cache\\update\\v1.1.0\\maalc-gui.exe: Access is denied. (os error 5)";
    const user = await open();
    await user.click(await screen.findByRole("button", { name: fill(zh["update.available"], v) }));
    await finish();
    expect(back.applies).toBe(1);
    expect(notice()).toHaveTextContent(fill(zh["update.apply_failed"], { ...v, error: `Error: ${back.applyFail}` }));
  });

  test("unsaved edits are saved before the window closes for the update", async () => {
    const user = await open();
    await user.click(screen.getByRole("checkbox", { name: fill(zh["tasks.tick"], { name: zh["task.AssembleModules"] }) }));
    await user.click(await screen.findByRole("button", { name: fill(zh["update.available"], v) }));
    await finish();
    expect(back.applies).toBe(1);
    expect(back.saved).toHaveLength(1);
    expect(JSON.parse(back.saved[0]).tasks.find((x: { id: string }) => x.id === "AssembleModules").enabled).toBe(true);
  });

  test("during a run the download goes on, but the apply waits until the run ends", async () => {
    const user = await open();
    await user.click(screen.getByRole("button", { name: zh["runner.start"] }));
    await waitFor(() => expect(back.send).toBeDefined());
    await user.click(await screen.findByRole("button", { name: fill(zh["update.available"], v) }));
    await finish();
    expect(back.applies).toBe(0);
    const wait = screen.getByRole("button", { name: fill(zh["update.after_run"], v) });
    expect(wait).toBeDisabled();
    expect(wait).toHaveAttribute("title", zh["update.after_run_title"]);
    act(() => { back.send!({ type: "event", event: "end", result: "succeeded" }); back.send!({ type: "exit", code: 0, ended: true, tail: [] }); });
    const apply = screen.getByRole("button", { name: fill(zh["update.apply"], v) });
    expect(apply).toBeEnabled();
    await user.click(apply);
    expect(back.applies).toBe(1);
  });

  test("an apply the backend refuses because a run started meanwhile waits for the run", async () => {
    back.applyFail = "a run is under way";
    const user = await open();
    await user.click(await screen.findByRole("button", { name: fill(zh["update.available"], v) }));
    await finish();
    expect(back.applies).toBe(1);
    expect(screen.getByRole("button", { name: fill(zh["update.apply"], v) })).toBeEnabled();
    expect(screen.queryByRole("alert", { name: zh["update.notice"] })).toBeNull();
  });
});

describe("how the last apply went", () => {
  const outcome = (o: Partial<UpdateOutcome>): UpdateOutcome => ({ state: "done", from: "1.0.0", to: "1.1.0", error: null, restored: true, ...o });

  test("an update that went through says so until dismissed", async () => {
    back.outcome = outcome({});
    back.release = null;
    const user = await open();
    const said = await screen.findByRole("status", { name: zh["update.notice"] });
    expect(said).toHaveTextContent(fill(zh["update.done"], { from: "1.0.0", to: "1.1.0" }));
    await user.click(screen.getByRole("button", { name: zh["update.dismiss"] }));
    expect(screen.queryByRole("status", { name: zh["update.notice"] })).toBeNull();
  });

  test("an update that failed and went back says why", async () => {
    back.outcome = outcome({ state: "failed", error: "cannot move C:\\maalc\\python aside: in use", restored: true });
    await open();
    expect(await screen.findByRole("alert", { name: zh["update.notice"] }))
      .toHaveTextContent(fill(zh["update.failed_restored"], { from: "1.0.0", to: "1.1.0", error: "cannot move C:\\maalc\\python aside: in use" }));
  });

  test("an update that did not all go back, or was cut short, says where the old files are", async () => {
    back.outcome = outcome({ state: "failed", error: "cannot copy the new agent: disk full", restored: false });
    await open();
    const said = await screen.findByRole("alert", { name: zh["update.notice"] });
    expect(said).toHaveTextContent("cannot copy the new agent: disk full");
    expect(said).toHaveTextContent("cache\\update\\old\\");
  });

  test("an apply cut short says so", async () => {
    back.outcome = outcome({ state: "applying", restored: false });
    await open();
    const said = await screen.findByRole("alert", { name: zh["update.notice"] });
    expect(said).toHaveTextContent(fill(zh["update.cut_short"], { from: "1.0.0", to: "1.1.0" }).split("\n")[0]);
    expect(said).toHaveTextContent("cache\\update\\old\\");
  });
});
