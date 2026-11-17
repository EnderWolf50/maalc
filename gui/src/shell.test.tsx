// The editor's shell (App.tsx): the main tabs from the keyboard, and the save state in the header when a save is refused.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import libRs from "../src-tauri/src/lib.rs?raw";
import App from "./App";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam } from "./model";
import { READ_BACK_FILES } from "./readBack";
import { queuedTeams, sideList } from "./testing";
import { cases, olderFile, v20File, v21File } from "./settingsCases";

const zh = TEXT.zh_tw;
// old: each [version, text] kept aside, oldFail the error that meets (#782); writes: the files written, in turn; back: the
// read-back files of config/ by name (#814), an Error one that cannot be read, reads the names read; agentFirst: the
// file the Agent writes just before the next save, which that save then meets (#501)
const file = vi.hoisted(() => ({
  text: "", saved: [] as string[], fail: "", old: [] as [number, string][], oldFail: "", writes: [] as string[],
  back: {} as Record<string, string | Error>, reads: [] as string[], agentFirst: null as string | null,
}));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: (text: string) => {
    if (file.fail) return Promise.reject(new Error(file.fail));
    if (file.agentFirst !== null) {
      file.text = file.agentFirst;
      file.agentFirst = null;
      return Promise.reject("settings.json changed on disk");
    }
    file.saved.push(text);
    file.writes.push("settings");
    file.text = text;
    return Promise.resolve();
  },
  loadReadBack: (name: string) => {
    file.reads.push(name);
    const f = file.back[name];
    return f instanceof Error ? Promise.reject(f) : Promise.resolve(f ?? null);
  },
  saveOldSettings: (version: number, text: string) => {
    if (file.oldFail) return Promise.reject(new Error(file.oldFail));
    file.old.push([version, text]);
    file.writes.push("old");
    return Promise.resolve();
  },
  rootDir: () => Promise.resolve("root"),
}));

/** Two enabled teams on game team slot 1: a save is refused (validate.ts crossCheck). */
function clash() {
  const s = newSettings();
  Object.assign(s, queuedTeams([newTeam(1, "Ta"), newTeam(2, "Tb")]));
  s.teams[1].game_team = 1;
  return JSON.stringify(s, null, 2) + "\n";
}

beforeEach(() => {
  file.text = JSON.stringify(newSettings(), null, 2) + "\n";
  file.saved = [];
  file.fail = "";
  file.old = [];
  file.oldFail = "";
  file.writes = [];
  file.back = {};
  file.reads = [];
  file.agentFirst = null;
});

test("the arrow keys move along the main tabs and open the one they reach; Home and End go to the ends", async () => {
  const user = userEvent.setup();
  render(<App start="teams" />);
  const teams = await screen.findByRole("tab", { name: zh["tab.teams"] });
  expect(teams).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("tab", { name: zh["tab.gifts"] })).toHaveAttribute("tabindex", "-1");
  teams.focus();
  await user.keyboard("{ArrowRight}{ArrowRight}");
  const deployment = screen.getByRole("tab", { name: zh["tab.deployment"] });
  expect(deployment).toHaveAttribute("aria-selected", "true");
  expect(deployment).toHaveFocus();
  await user.keyboard("{ArrowLeft}");
  expect(screen.getByRole("tab", { name: zh["tab.gifts"] })).toHaveFocus();
  await user.keyboard("{End}");
  expect(screen.getByRole("tab", { name: zh["tab.trials"] })).toHaveAttribute("aria-selected", "true");
  await user.keyboard("{Home}");
  const run = screen.getByRole("tab", { name: zh["tab.run"] });
  expect(run).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", run.id);
});

test("the tabs come in four groups: what runs, the team, the plans, the overrides (#721, #814)", async () => {
  render(<App start="teams" />);
  await screen.findByRole("tab", { name: zh["tab.teams"] });
  // a separator between two groups shows as "|"
  const row = [...screen.getByRole("tablist").children].map((x) => (x.getAttribute("role") === "tab" ? x.textContent : "|"));
  expect(row).toEqual([
    zh["tab.run"], "|", zh["tab.teams"], zh["tab.gifts"], "|",
    zh["tab.deployment"], zh["tab.starlight"], zh["tab.themepacks"], "|", zh["tab.events"], zh["tab.trials"],
  ]);
});

test("one Run tab holds what the Run options and Daily tabs held, with the task list (#814); the window opens on it (#815)", async () => {
  render(<App />);
  await screen.findByRole("tab", { name: zh["tab.teams"] });
  const tabs = screen.getAllByRole("tab").map((x) => x.textContent);
  expect(tabs).not.toContain("執行選項");
  expect(tabs).not.toContain("日常");
  expect(tabs.filter((x) => x === zh["tab.run"])).toHaveLength(1);
  expect(screen.getByRole("tab", { name: zh["tab.run"] })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: zh["runner.start"] })).toBeVisible();
});

test("a problem in a task's option opens the Run tab with that task picked, its field focused", async () => {
  const s = newSettings();
  s.luxcavation.thread.retries = -1; // the schema's minimum is 0
  file.text = JSON.stringify(s, null, 2) + "\n";
  const user = userEvent.setup();
  render(<App start="teams" />);
  const problems = await screen.findByRole("alert");
  expect(screen.getByRole("tab", { name: zh["tab.run"] })).toHaveClass("bad");
  await user.click(within(problems).getByRole("button"));
  expect(screen.getByRole("heading", { name: /紐本.*ThreadLuxcavation/ })).toBeVisible();
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: new RegExp(zh["lux.retries"]) })).toHaveFocus());
  expect(document.querySelector(".task-list li.selected")).toHaveClass("bad");
});

describe("an older file (#782, #813)", () => {
  const write = (data: unknown) => (file.text = JSON.stringify(data, null, 2) + "\n");

  test("a version 20 file is kept beside it, then written back as version 23 with its own run options", async () => {
    const text = write(v20File([{ set: "run/difficulty", value: "hard" }, { set: "luxcavation/exp/team", value: "b" }]));
    render(<App start="teams" />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect([file.old, file.writes]).toEqual([[[20, text]], ["old", "settings"]]);
    const saved = JSON.parse(file.saved[0]);
    expect([saved.version, saved.team_queue, saved.run.difficulty, saved.run.start_team, saved.luxcavation.exp.team])
      .toEqual([23, ["a", "b"], "hard", null, "b"]);
    expect(saved.tasks).toEqual(cases.valid.tasks); // the sections version 23 added, at their defaults
  });

  test("a version 22 file gets the task options at their defaults", async () => {
    write(olderFile(22));
    render(<App start="teams" />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.old[0][0]).toBe(22);
    const saved = JSON.parse(file.saved[0]);
    expect({ ...saved, gift_lists: null }).toEqual({ ...cases.valid, gift_lists: null });
  });

  test("a version 21 file is written back with the queue in the order of its list", async () => {
    // the list b, a: the queue starts at b, as before the upgrade
    const old = v21File([{ set: "teams/0/id", value: "b" }, { set: "teams/1/id", value: "a" }]);
    const text = write(old);
    render(<App start="teams" />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.old).toEqual([[21, text]]);
    expect(JSON.parse(file.saved[0]).team_queue).toEqual(["b", "a"]);
  });

  test("a file the checks refuse is kept aside and waits for a save", async () => {
    write(v20File([{ set: "teams/1/game_team", value: 1 }])); // two enabled teams on TEAMS #1
    const user = userEvent.setup();
    render(<App start="teams" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(zh.saveBlocked);
    expect(file.writes).toEqual(["old"]);
    await user.click(within(document.querySelector("aside")!).getByText("Team b"));
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["team.game_team"] }), { target: { value: "2" } });
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.writes).toEqual(["old", "settings"]);
    expect(JSON.parse(file.saved[0]).version).toBe(23);
  });

  test("when it cannot be kept aside the window says why and writes nothing", async () => {
    write(v20File());
    file.oldFail = "access denied";
    render(<App start="teams" />);
    expect(await screen.findByText(zh.loadError)).toBeInTheDocument();
    expect(screen.getByText(/access denied/)).toBeInTheDocument();
    expect(file.writes).toEqual([]);
  });

  test("the file it is kept as is config/settings.v<version>.json (src-tauri lib.rs old_settings_name)", () => {
    // where the read-back of an older install's values looks (spec #811)
    expect(libRs).toContain('format!("settings.v{version}.json")');
  });
});

describe("the read-back of a v1.0.0 install's run values (#814)", () => {
  const write = (data: unknown) => (file.text = JSON.stringify(data, null, 2) + "\n");
  const opt = (type: string, v: Record<string, unknown>) => ({ type, ...v });
  /** MXU's config file: Mirror Dungeon on hard from a team deleted since, EXP Luxcavation on team a, the webhook encrypted. */
  const mxu = JSON.stringify({
    version: "1.0", lastActiveInstanceId: "i1",
    instances: [{
      id: "i1", name: "Main", controllerName: "MuMu", savedDevice: { adbDeviceName: "MuMu", adbDeviceAddress: "127.0.0.1:16384" },
      tasks: [
        { id: "t1", taskName: "MirrorDungeon", enabled: true, optionValues: {
          MirrorDifficulty: opt("select", { caseName: "hard" }), MirrorStartTeam: opt("select", { caseName: "gone" }),
        } },
        { id: "t2", taskName: "ExpLuxcavation", enabled: true, optionValues: { ExpTeam: opt("select", { caseName: "a" }) } },
      ],
    }],
    globalOptionValues: { WebhookUrl: opt("input", { values: { url: "" }, encryptedValues: { url: "eA==" } }) },
  });
  const notice = () => screen.findByRole("region", { name: zh["rb.title"] });

  test("a version 22 file is written as 23 with MXU's values, and the notice lists what came back and what did not, once", async () => {
    write(olderFile(22));
    file.back = { "mxu-maalc.json": mxu };
    const user = userEvent.setup();
    render(<App start="teams" />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved = JSON.parse(file.saved[0]);
    expect([saved.version, saved.run.difficulty, saved.run.start_team, saved.luxcavation.exp.team, saved.emulator.address])
      .toEqual([23, "hard", null, "a", "127.0.0.1:16384"]);
    expect(saved.tasks.slice(0, 2)).toEqual([{ id: "MirrorDungeon", enabled: true }, { id: "ExpLuxcavation", enabled: true }]);
    // MXU's file and the others are only read
    expect(file.writes).toEqual(["old", "settings"]);
    expect([...file.reads].sort()).toEqual(["mxu-maalc.json", "settings.v20.json", "team_options.json"]);
    const shown = await notice();
    for (const text of [
      fill(zh["rb.from_mxu"], { version: 22, instance: "Main" }),
      fill(zh["rb.row"], { where: "鏡牢 · 難度", value: "困難" }),
      fill(zh["rb.row"], { where: "經驗本 · 隊伍", value: "Team a（TEAMS #1）" }),
      fill(zh["rb.tasks"], { tasks: "鏡牢、經驗本" }),
      fill(zh["rb.address"], { address: "127.0.0.1:16384" }),
      zh["rb.missed"], zh["rb.webhook"],
      fill(zh["rb.team"], { where: "鏡牢 · 這次從哪一支隊伍開始", team: "gone", none: "照隊伍佇列" }),
    ]) expect(shown).toHaveTextContent(text);
    // over every tab, until dismissed
    await user.click(screen.getByRole("tab", { name: zh["tab.gifts"] }));
    await user.click(within(await notice()).getByRole("button", { name: zh["rb.dismiss"] }));
    expect(screen.queryByRole("region", { name: zh["rb.title"] })).toBeNull();
  });

  test("in English too", async () => {
    write(olderFile(22, [{ set: "language", value: "en_us" }]));
    file.back = { "mxu-maalc.json": mxu };
    render(<App start="teams" />);
    const shown = await screen.findByRole("region", { name: TEXT.en_us["rb.title"] });
    expect(shown).toHaveTextContent(fill(TEXT.en_us["rb.row"], { where: "Mirror Dungeon · Difficulty", value: "Hard" }));
    expect(shown).toHaveTextContent(TEXT.en_us["rb.webhook"]);
  });

  test("with neither MXU's file nor settings.v20.json, the notice says the options are at their defaults, no task ticked", async () => {
    write(olderFile(22));
    render(<App start="teams" />);
    const shown = await notice();
    expect(shown).toHaveTextContent(fill(zh["rb.from_defaults"], { version: 22 }));
    expect(shown).toHaveTextContent(fill(zh["rb.absent"], { files: "mxu-maalc.json、settings.v20.json" }));
    expect(shown).toHaveTextContent(zh["rb.read_none"]);
    expect(shown).toHaveTextContent(zh["rb.tasks_default"]);
    expect(JSON.parse(file.saved[0]).tasks).toEqual(cases.valid.tasks);
  });

  test("a version 23 file reads nothing back and shows no notice", async () => {
    file.back = { "mxu-maalc.json": mxu };
    render(<App start="teams" />);
    await screen.findByRole("button", { name: zh.save });
    expect(file.reads).toEqual([]);
    expect(screen.queryByRole("region", { name: zh["rb.title"] })).toBeNull();
  });

  test("a file the checks refuse shows its notice once the save that fixes it writes it", async () => {
    write(olderFile(22, [{ set: "teams/1/game_team", value: 1 }])); // two enabled teams on TEAMS #1
    file.back = { "mxu-maalc.json": mxu };
    const user = userEvent.setup();
    render(<App start="teams" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(zh.saveBlocked);
    expect(screen.queryByRole("region", { name: zh["rb.title"] })).toBeNull();
    await user.click(screen.getByRole("tab", { name: zh["tab.teams"] }));
    await user.click(within(document.querySelector("aside")!).getByText("Team b"));
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["team.game_team"] }), { target: { value: "2" } });
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).run.difficulty).toBe("hard");
    expect(await notice()).toHaveTextContent(fill(zh["rb.from_mxu"], { version: 22, instance: "Main" }));
  });

  test("the Agent's write of the old file before the write-back keeps the values read back", async () => {
    const old = olderFile(22);
    write(old);
    file.back = { "mxu-maalc.json": mxu };
    // the Agent moves team a to the end of the queue and writes the file at its own version (spec 04 section 2)
    file.agentFirst = JSON.stringify({ ...old, team_queue: ["b", "a"] }, null, 2) + "\n";
    const user = userEvent.setup();
    render(<App start="teams" />);
    await waitFor(() => expect(file.agentFirst).toBeNull());
    act(() => { window.dispatchEvent(new Event("focus")); }); // the editor reads the file again
    expect(await screen.findByText(zh.diskChanged)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved = JSON.parse(file.saved[0]);
    expect([saved.version, saved.team_queue, saved.run.difficulty, saved.luxcavation.exp.team]).toEqual([23, ["b", "a"], "hard", "a"]);
    expect(await notice()).toBeVisible();
  });

  test("an unreadable file is said so, and the next one is read", async () => {
    write(olderFile(22));
    file.back = { "mxu-maalc.json": new Error("access denied"), "settings.v20.json": JSON.stringify(v20File([{ set: "run/difficulty", value: "normal" }])) };
    render(<App start="teams" />);
    const shown = await notice();
    expect(shown).toHaveTextContent(fill(zh["rb.problem"], { why: "mxu-maalc.json: Error: access denied" }));
    expect(shown).toHaveTextContent(fill(zh["rb.from_v20"], { version: 22 }));
    expect(shown).not.toHaveTextContent("config/ 裡沒有這些檔"); // it is there, and could not be read
    // settings.v20.json's other task options at their defaults: run's 14, 5 for each Luxcavation task and Charge's 1, less the one
    expect(shown).toHaveTextContent(fill(zh["rb.same"], { n: 24 }));
    expect(JSON.parse(file.saved[0]).run.difficulty).toBe("normal");
  });

  test("the files it reads are the three lib.rs load_read_back allows", () => {
    const names = Object.values(READ_BACK_FILES).map((x) => `"${x}"`).join(", ");
    expect(libRs).toContain(`const READ_BACK: [&str; 3] = [${names}];`);
  });
});

test("a save keeps the task options, the task list, the emulator and the schedules it has no editor for (#813)", async () => {
  const s = newSettings();
  Object.assign(s, queuedTeams([newTeam(1, "Ta")]));
  s.run = { ...s.run, difficulty: "hard", runs: null, start_team: s.teams[0].id, webhook_url: "http://hook.invalid/" };
  s.luxcavation.thread = { ...s.luxcavation.thread, mode: "count", team: s.teams[0].id };
  s.charge_enkephalin.count = 4;
  s.tasks = [{ id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: true }];
  s.emulator = { address: "127.0.0.1:16384", mumu_index: 0, mumu_manager: "MuMu/nx_main/MuMuManager.exe" };
  s.schedules = [{ id: "s1", days: ["mon", "thu"], time: "05:10", wake: false }];
  file.text = JSON.stringify(s, null, 2) + "\n";
  const user = userEvent.setup();
  render(<App start="teams" />);
  await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
  await user.click(screen.getByRole("button", { name: zh.save }));
  await waitFor(() => expect(file.saved).toHaveLength(1));
  const saved = JSON.parse(file.saved[0]);
  expect(saved.teams[0].name).toBe("Ta!");
  const kept = ["run", "luxcavation", "charge_enkephalin", "emulator", "schedules"] as const;
  expect(Object.fromEntries(kept.map((k) => [k, saved[k]]))).toEqual(Object.fromEntries(kept.map((k) => [k, s[k]])));
  // the tasks the list left out come last, unticked (#814)
  expect(saved.tasks).toEqual([...s.tasks, ...cases.valid.tasks.filter((x) => !s.tasks.some((y) => y.id === x.id))]);
});

test("with nothing edited the header says there is nothing to save", async () => {
  render(<App start="teams" />);
  await screen.findByRole("button", { name: zh.save });
  expect(document.querySelector(".status")).toHaveAttribute("data-state", "clean");
  expect(document.querySelector(".status")).toHaveTextContent(zh["saveState.clean"]);
});

test("a write that fails shows as a failure in the header, not as plain unsaved changes; the next good save clears it", async () => {
  const s = newSettings();
  Object.assign(s, queuedTeams([newTeam(1, "Ta")]));
  file.text = JSON.stringify(s, null, 2) + "\n";
  file.fail = "disk full";
  const user = userEvent.setup();
  render(<App start="teams" />);
  await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
  const save = screen.getByRole("button", { name: zh.save });
  await user.click(save);
  await waitFor(() => expect(document.querySelector(".status")).toHaveAttribute("data-state", "failed"));
  expect(document.querySelector(".status")).toHaveTextContent("disk full");
  expect(save).toHaveClass("refused");
  file.fail = "";
  await user.click(save);
  await waitFor(() => expect(document.querySelector(".status")).toHaveAttribute("data-state", "saved"));
  expect(save).not.toHaveClass("refused");
});

test("a refused save shows in the header with the number of problems, also when nothing was edited", async () => {
  file.text = clash();
  const user = userEvent.setup();
  render(<App start="teams" />);
  const save = await screen.findByRole("button", { name: zh.save });
  await user.click(save);
  await waitFor(() => expect(document.querySelector(".status")).toHaveAttribute("data-state", "blocked"));
  expect(document.querySelector(".status")).toHaveTextContent(fill(zh["saveState.refused"], { n: 1 }));
  expect(save).not.toHaveClass("armed");
  expect(file.saved).toEqual([]);
});

test("a problem made after a good save asks to fix it before saving: no save was refused", async () => {
  const ok = newSettings();
  Object.assign(ok, queuedTeams([newTeam(1, "Ta"), newTeam(2, "Tb")]));
  file.text = JSON.stringify(ok, null, 2) + "\n";
  const user = userEvent.setup();
  render(<App start="teams" />);
  const save = await screen.findByRole("button", { name: zh.save });
  await user.click(save);
  await waitFor(() => expect(document.querySelector(".status")).toHaveAttribute("data-state", "saved"));
  await user.click(sideList().getAllByRole("listitem")[1]);
  const slot = screen.getByRole("spinbutton", { name: zh["team.game_team"] });
  fireEvent.change(slot, { target: { value: "1" } });
  const plate = document.querySelector(".status")!;
  expect(plate).toHaveAttribute("data-state", "blocked");
  expect(plate).toHaveTextContent(fill(zh["saveState.toFix"], { n: 1 }));
  expect(plate).not.toHaveTextContent(fill(zh["saveState.refused"], { n: 1 }));
  await user.click(save);
  expect(document.querySelector(".status")).toHaveTextContent(fill(zh["saveState.refused"], { n: 1 }));
});

test("an edit after a refused save still shows the refusal, with the unsaved changes", async () => {
  file.text = clash();
  const user = userEvent.setup();
  render(<App start="teams" />);
  await user.click(await screen.findByRole("button", { name: zh.save }));
  await user.type(screen.getByRole("textbox", { name: zh.name }), "!");
  expect(document.querySelector(".status")).toHaveAttribute("data-state", "blocked");
  expect(document.querySelector(".status")).toHaveTextContent(fill(zh["saveState.refused"], { n: 1 }));
  expect(document.querySelector(".status")).toHaveTextContent(zh.unsaved);
});

test("a problem typed before any save says Save must wait, on the plate and on Save, with the field marked, once the field is left", async () => {
  const ok = newSettings();
  Object.assign(ok, queuedTeams([newTeam(1, "Ta"), newTeam(2, "Tb")]));
  file.text = JSON.stringify(ok, null, 2) + "\n";
  const user = userEvent.setup();
  render(<App start="teams" />);
  const save = await screen.findByRole("button", { name: zh.save });
  await user.click(sideList().getAllByRole("listitem")[1]);
  const slot = screen.getByRole("spinbutton", { name: zh["team.game_team"] });
  await user.type(slot, "{Backspace}"); // TEAMS #2 emptied: the lowest, #1, the first team's
  const plate = document.querySelector(".status")!;
  expect(plate).toHaveAttribute("data-state", "dirty"); // still being typed in
  expect(save).toHaveClass("armed");
  await user.tab();
  expect(plate).toHaveAttribute("data-state", "blocked");
  expect(plate).toHaveTextContent(fill(zh["saveState.toFix"], { n: 1 }));
  expect(save).toHaveClass("refused");
  expect(save).not.toHaveClass("armed");
  expect(slot).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByRole("alert")).toHaveTextContent(zh.saveBlocked);
});

describe("Revert", () => {
  const edited = async () => {
    const ok = newSettings();
    Object.assign(ok, queuedTeams([newTeam(1, "Ta")]));
    file.text = JSON.stringify(ok, null, 2) + "\n";
    const user = userEvent.setup();
    render(<App start="teams" />);
    await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
    return user;
  };

  test("shows only while there are unsaved changes", async () => {
    render(<App start="teams" />);
    await screen.findByRole("button", { name: zh.save });
    expect(screen.queryByRole("button", { name: zh.revert })).toBeNull();
  });

  test("puts the file's settings back, says so, and Undo brings the edits back", async () => {
    const user = await edited();
    await user.click(screen.getByRole("button", { name: zh.revert }));
    expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("Ta");
    const plate = document.querySelector(".status")!;
    expect(plate).toHaveTextContent(zh.reverted);
    expect(plate).not.toHaveTextContent(zh.unsaved);
    await user.click(screen.getByRole("button", { name: zh.undo }));
    expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("Ta!");
    expect(document.querySelector(".status")).toHaveTextContent(zh.unsaved);
    expect(file.saved).toEqual([]);
  });

  test("an edit after it drops the Undo: the edits it would bring back are no longer the newest", async () => {
    const user = await edited();
    await user.click(screen.getByRole("button", { name: zh.revert }));
    await user.type(screen.getByRole("textbox", { name: zh.name }), "?");
    expect(screen.queryByRole("button", { name: zh.undo })).toBeNull();
    expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("Ta?");
  });
});

test("the header's file path, cut short in a narrow window, shows in full on hover", async () => {
  render(<App start="teams" />);
  await screen.findByRole("button", { name: zh.save });
  expect(document.querySelector("header .path")).toHaveAttribute("title", "root\\config\\settings.json");
});

test("after 放棄變更, an edit and its undoing drop the Undo: the edits it would bring back are no longer the newest", async () => {
  const ok = newSettings();
  Object.assign(ok, queuedTeams([newTeam(1, "Ta")]));
  file.text = JSON.stringify(ok, null, 2) + "\n";
  const user = userEvent.setup();
  render(<App start="teams" />);
  await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
  await user.click(screen.getByRole("button", { name: zh.revert }));
  await user.type(screen.getByRole("textbox", { name: zh.name }), "?{Backspace}");
  expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("Ta");
  expect(screen.queryByRole("button", { name: zh.undo })).toBeNull();
});
