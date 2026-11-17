// The editor's shell (App.tsx): the main tabs from the keyboard, and the save state in the header when a save is refused.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import libRs from "../src-tauri/src/lib.rs?raw";
import App from "./App";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam } from "./model";
import { queuedTeams, sideList } from "./testing";
import { cases, olderFile, v20File, v21File } from "./settingsCases";

const zh = TEXT.zh_tw;
// old: each [version, text] kept aside, oldFail the error that meets (#782); writes: the files written, in turn
const file = vi.hoisted(() => ({
  text: "", saved: [] as string[], fail: "", old: [] as [number, string][], oldFail: "", writes: [] as string[],
}));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: (text: string) => {
    if (file.fail) return Promise.reject(new Error(file.fail));
    file.saved.push(text);
    file.writes.push("settings");
    return Promise.resolve();
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
});

test("the arrow keys move along the main tabs and open the one they reach; Home and End go to the ends", async () => {
  const user = userEvent.setup();
  render(<App />);
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
  expect(teams).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", teams.id);
});

test("the tabs come in three groups: the team, the plans, the overrides (#721)", async () => {
  render(<App />);
  await screen.findByRole("tab", { name: zh["tab.teams"] });
  // a separator between two groups shows as "|"
  const row = [...screen.getByRole("tablist").children].map((x) => (x.getAttribute("role") === "tab" ? x.textContent : "|"));
  expect(row).toEqual([
    zh["tab.teams"], zh["tab.gifts"], "|",
    zh["tab.deployment"], zh["tab.starlight"], zh["tab.themepacks"], "|", zh["tab.events"], zh["tab.trials"],
  ]);
});

test("no Run options or Daily tab: the task options are the settings file's again (#813), and the runner's tab edits them (#811)", async () => {
  render(<App />);
  await screen.findByRole("tab", { name: zh["tab.teams"] });
  const tabs = screen.getAllByRole("tab").map((x) => x.textContent);
  expect(tabs).not.toContain("執行選項");
  expect(tabs).not.toContain("日常");
  expect(tabs).toHaveLength(7);
});

describe("an older file (#782, #813)", () => {
  const write = (data: unknown) => (file.text = JSON.stringify(data, null, 2) + "\n");

  test("a version 20 file is kept beside it, then written back as version 23 with its own run options", async () => {
    const text = write(v20File([{ set: "run/difficulty", value: "hard" }, { set: "luxcavation/exp/team", value: "b" }]));
    render(<App />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect([file.old, file.writes]).toEqual([[[20, text]], ["old", "settings"]]);
    const saved = JSON.parse(file.saved[0]);
    expect([saved.version, saved.team_queue, saved.run.difficulty, saved.run.start_team, saved.luxcavation.exp.team])
      .toEqual([23, ["a", "b"], "hard", null, "b"]);
    expect(saved.tasks).toEqual(cases.valid.tasks); // the sections version 23 added, at their defaults
  });

  test("a version 22 file gets the task options at their defaults", async () => {
    write(olderFile(22));
    render(<App />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.old[0][0]).toBe(22);
    const saved = JSON.parse(file.saved[0]);
    expect({ ...saved, gift_lists: null }).toEqual({ ...cases.valid, gift_lists: null });
  });

  test("a version 21 file is written back with the queue in the order of its list", async () => {
    // the list b, a: the queue starts at b, as before the upgrade
    const old = v21File([{ set: "teams/0/id", value: "b" }, { set: "teams/1/id", value: "a" }]);
    write(old);
    render(<App />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.old).toEqual([[21, file.text]]);
    expect(JSON.parse(file.saved[0]).team_queue).toEqual(["b", "a"]);
  });

  test("a file the checks refuse is kept aside and waits for a save", async () => {
    write(v20File([{ set: "teams/1/game_team", value: 1 }])); // two enabled teams on TEAMS #1
    const user = userEvent.setup();
    render(<App />);
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
    render(<App />);
    expect(await screen.findByText(zh.loadError)).toBeInTheDocument();
    expect(screen.getByText(/access denied/)).toBeInTheDocument();
    expect(file.writes).toEqual([]);
  });

  test("the file it is kept as is config/settings.v<version>.json (src-tauri lib.rs old_settings_name)", () => {
    // where the read-back of an older install's values looks (spec #811)
    expect(libRs).toContain('format!("settings.v{version}.json")');
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
  render(<App />);
  await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
  await user.click(screen.getByRole("button", { name: zh.save }));
  await waitFor(() => expect(file.saved).toHaveLength(1));
  const saved = JSON.parse(file.saved[0]);
  expect(saved.teams[0].name).toBe("Ta!");
  const kept = ["run", "luxcavation", "charge_enkephalin", "tasks", "emulator", "schedules"] as const;
  expect(Object.fromEntries(kept.map((k) => [k, saved[k]]))).toEqual(Object.fromEntries(kept.map((k) => [k, s[k]])));
});

test("with nothing edited the header says there is nothing to save", async () => {
  render(<App />);
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
  render(<App />);
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
  render(<App />);
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
  render(<App />);
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
  render(<App />);
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
  render(<App />);
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
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
    return user;
  };

  test("shows only while there are unsaved changes", async () => {
    render(<App />);
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
  render(<App />);
  await screen.findByRole("button", { name: zh.save });
  expect(document.querySelector("header .path")).toHaveAttribute("title", "root\\config\\settings.json");
});

test("after 放棄變更, an edit and its undoing drop the Undo: the edits it would bring back are no longer the newest", async () => {
  const ok = newSettings();
  Object.assign(ok, queuedTeams([newTeam(1, "Ta")]));
  file.text = JSON.stringify(ok, null, 2) + "\n";
  const user = userEvent.setup();
  render(<App />);
  await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
  await user.click(screen.getByRole("button", { name: zh.revert }));
  await user.type(screen.getByRole("textbox", { name: zh.name }), "?{Backspace}");
  expect(screen.getByRole("textbox", { name: zh.name })).toHaveValue("Ta");
  expect(screen.queryByRole("button", { name: zh.undo })).toBeNull();
});
