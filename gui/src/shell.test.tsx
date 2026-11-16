// The editor's shell (App.tsx): the main tabs from the keyboard, and the save state in the header when a save is refused.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import libRs from "../src-tauri/src/lib.rs?raw";
import App from "./App";
import { TEXT, fill } from "./i18n";
import { MOVED, newSettings, newTeam } from "./model";
import { queuedTeams, sideList } from "./testing";
import { v20File, v21File, type Edit } from "./settingsCases";

const zh = TEXT.zh_tw;
// teamOptions: the team options file's text (null: none), teamWrites each text written to it, teamFail the error its write
// meets (#780); old each [version, text] kept aside, oldFail the error that meets (#782); writes the files written, in turn
const file = vi.hoisted(() => ({
  text: "", saved: [] as string[], fail: "", teamOptions: null as string | null, teamWrites: [] as string[], teamFail: "",
  old: [] as [number, string][], oldFail: "", writes: [] as string[],
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
  loadTeamOptions: () => Promise.resolve(file.teamOptions),
  saveTeamOptions: (text: string) => {
    if (file.teamFail) return Promise.reject(new Error(file.teamFail));
    file.teamWrites.push(text);
    file.teamOptions = text;
    file.writes.push("team options");
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
  file.teamOptions = null;
  file.teamWrites = [];
  file.teamFail = "";
  file.old = [];
  file.oldFail = "";
  file.writes = [];
});

/** The team ids of the team options file's ExpTeam cases, in order (teamOptions.ts). */
const teamCases = () => (JSON.parse(file.teamOptions!).option.ExpTeam.cases as { name: string }[]).map((c) => c.name);

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

test("the tabs come in three groups: the team, the plans, the overrides (#721; the daily tasks' went to the client, #780)", async () => {
  render(<App />);
  await screen.findByRole("tab", { name: zh["tab.teams"] });
  // a separator between two groups shows as "|"
  const row = [...screen.getByRole("tablist").children].map((x) => (x.getAttribute("role") === "tab" ? x.textContent : "|"));
  expect(row).toEqual([
    zh["tab.teams"], zh["tab.gifts"], "|",
    zh["tab.deployment"], zh["tab.starlight"], zh["tab.themepacks"], "|", zh["tab.events"], zh["tab.trials"],
  ]);
});

test("the Run options and Daily tabs are gone: what they set is the client's task options (#779, #780, #781)", async () => {
  render(<App />);
  await screen.findByRole("tab", { name: zh["tab.teams"] });
  const tabs = screen.getAllByRole("tab").map((x) => x.textContent);
  expect(tabs).not.toContain("執行選項");
  expect(tabs).not.toContain("日常");
  expect(tabs).toHaveLength(7);
});

describe("the team options file (#780)", () => {
  const twoTeams = () => {
    const s = newSettings();
    Object.assign(s, queuedTeams([newTeam(1, "Ta"), newTeam(2, "Tb")]));
    file.text = JSON.stringify(s, null, 2) + "\n";
    return s;
  };

  test("the start writes it when it is not there, and the header says to reopen the client", async () => {
    const s = twoTeams();
    render(<App />);
    await waitFor(() => expect(file.teamWrites).toHaveLength(1));
    expect(teamCases()).toEqual(["none", ...s.teams.map((t) => t.id)]);
    await waitFor(() => expect(document.querySelector(".status")).toHaveTextContent(zh["teamOptions.updated"]));
  });

  test("a save that changes the team list writes it and says so once; a save that does not, writes nothing", async () => {
    const s = twoTeams();
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(file.teamWrites).toHaveLength(1)); // the start's
    await user.click(screen.getByRole("button", { name: `+ ${zh.add}` }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const added = JSON.parse(file.saved[0]).teams[2].id;
    expect(file.teamWrites).toHaveLength(2);
    expect(teamCases()).toEqual(["none", s.teams[0].id, s.teams[1].id, added]);
    const plate = document.querySelector(".status")!;
    expect(plate).toHaveAttribute("data-state", "saved");
    expect(plate).toHaveTextContent(zh.savedTeams);
    // a team's slot is in its label: written again; whether it is enabled is not: nothing written
    await user.click(sideList().getAllByRole("listitem")[1]);
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["team.game_team"] }), { target: { value: "5" } });
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(2));
    expect(file.teamWrites).toHaveLength(3);
    expect(JSON.parse(file.teamOptions!).option.ExpTeam.cases[2].label).toBe("Tb（TEAMS #5）");
    await user.click(screen.getByRole("checkbox", { name: new RegExp(zh["team.enabled"]) }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(3));
    expect(file.teamWrites).toHaveLength(3);
    expect(plate).toHaveTextContent(zh.saved);
    expect(plate).not.toHaveTextContent(zh["teamOptions.updated"]);
  });

  test("a write of it that fails says so, at the start and after a save that went through", async () => {
    twoTeams();
    file.teamFail = "disk full";
    const user = userEvent.setup();
    render(<App />);
    await user.type(await screen.findByRole("textbox", { name: zh.name }), "!");
    const plate = document.querySelector(".status")!;
    expect(plate).toHaveTextContent(fill(zh["teamOptions.failed"], { error: "Error: disk full" })); // beside unsaved
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    await waitFor(() => expect(plate).toHaveTextContent(fill(zh.savedTeamsFailed, { error: "Error: disk full" })));
    expect(file.teamWrites).toEqual([]);
  });

  test("a save the checks refuse writes neither file", async () => {
    file.text = clash();
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: zh.save }));
    await waitFor(() => expect(document.querySelector(".status")).toHaveAttribute("data-state", "blocked"));
    expect(file.teamWrites).toEqual([]); // not at the start either: the checks refuse the file's teams
  });
});

describe("a version 20 file (#782)", () => {
  /** settings_cases' valid file at version 20 with the three sections it had, these edits made, as the file. */
  const v20 = (edits: Edit[] = []) => (file.text = JSON.stringify(v20File(edits), null, 2) + "\n");
  const list = () => screen.queryByRole("region", { name: zh["moved.title"] });
  const defaults = () => {
    const option = JSON.parse(file.teamOptions!).option;
    return [option.ExpTeam.default_case, option.ThreadTeam.default_case];
  };

  test("is written back as version 22 in one go, without the three sections, the queue in the order of its teams", async () => {
    v20();
    render(<App />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved = JSON.parse(file.saved[0]);
    expect([saved.version, saved.team_queue]).toEqual([22, ["a", "b"]]);
    expect(MOVED.filter((k) => k in saved)).toEqual([]);
  });

  test("is kept beside it as it was, before anything is written", async () => {
    const text = v20();
    render(<App />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.old).toEqual([[20, text]]);
    expect(file.writes).toEqual(["old", "team options", "settings"]);
  });

  test("gives a first team options file the teams it picked, before the write-back", async () => {
    v20([{ set: "luxcavation/exp/team", value: "b" }]);
    render(<App />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(defaults()).toEqual(["b", "none"]);
  });

  test("lists once the values off the client's default, by the client's names, the webhook only as set", async () => {
    v20([{ set: "run/target_floor", value: 15 }, { set: "run/runs", value: null },
      { set: "run/webhook_url", value: "http://hook.invalid/secret" }, { set: "charge_enkephalin/count", value: 3 },
      { set: "luxcavation/thread/team", value: "a" }]);
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(list()).not.toBeNull());
    expect(within(list()!).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "全域選項 › 失敗通知 webhook：有設定", "鏡牢 › 目標層數：15 層（極限）", "鏡牢 › 限制局數：關",
      "紐本 › 隊伍：Team a（TEAMS #1）", "狂氣換腦啡肽 › 今天換到第幾次（目標 Daily Count）：3",
    ]);
    expect(list()).toHaveTextContent("config\\settings.v20.json");
    expect(document.body).not.toHaveTextContent("hook.invalid");
    await user.click(within(list()!).getByRole("button", { name: zh["moved.dismiss"] }));
    expect(list()).toBeNull();
  });

  test("every moved value at the client's default: nothing to list", async () => {
    v20();
    render(<App />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(list()).toBeNull();
  });

  test("a file the checks refuse is kept aside and waits for a save, which writes the team options file first", async () => {
    v20([{ set: "teams/1/game_team", value: 1 }, { set: "luxcavation/exp/team", value: "b" },
      { set: "run/target_floor", value: 10 }]); // two enabled teams on TEAMS #1
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(zh.saveBlocked);
    expect([file.writes, list()]).toEqual([["old"], null]); // not written back: nothing listed yet
    await user.click(within(document.querySelector("aside")!).getByText("Team b"));
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["team.game_team"] }), { target: { value: "2" } });
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.writes).toEqual(["old", "team options", "settings"]);
    expect(defaults()).toEqual(["b", "none"]);
    expect(within(list()!).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "鏡牢 › 目標層數：10 層（無限）", "經驗本 › 隊伍：Team b（TEAMS #2）",
    ]);
  });

  test("a save of it that cannot write the team options file writes nothing, as the start; the next save does", async () => {
    v20([{ set: "teams/1/game_team", value: 1 }, { set: "luxcavation/exp/team", value: "b" }]);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("alert");
    await user.click(within(document.querySelector("aside")!).getByText("Team b"));
    fireEvent.change(screen.getByRole("spinbutton", { name: zh["team.game_team"] }), { target: { value: "2" } });
    file.teamFail = "disk full";
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(document.querySelector(".status")).toHaveAttribute("data-state", "failed"));
    expect(document.querySelector(".status")).toHaveTextContent("disk full");
    expect([file.writes, file.saved]).toEqual([["old"], []]);
    file.teamFail = "";
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.writes).toEqual(["old", "team options", "settings"]);
    expect(defaults()).toEqual(["b", "none"]);
  });

  test("a team options file that cannot be written leaves the old file as it is, for the next start", async () => {
    v20([{ set: "luxcavation/exp/team", value: "b" }]);
    file.teamFail = "disk full";
    render(<App />);
    await waitFor(() => expect(document.querySelector(".status")).toHaveTextContent("disk full"));
    expect([file.writes, file.saved, list()]).toEqual([["old"], [], null]);
  });

  test("when it cannot be kept aside the window says why and writes nothing", async () => {
    v20();
    file.oldFail = "access denied";
    render(<App />);
    expect(await screen.findByText(zh.loadError)).toBeInTheDocument();
    expect(screen.getByText(/access denied/)).toBeInTheDocument();
    expect(file.writes).toEqual([]);
  });

  test("the file it is kept as is the one the window names (src-tauri lib.rs old_settings_name)", () => {
    expect(libRs).toContain('format!("settings.v{version}.json")');
    for (const lang of ["zh_tw", "en_us"] as const) expect(TEXT[lang]["moved.note"]).toContain("config\\settings.v{version}.json");
  });
});

describe("a version 21 file (#803)", () => {
  test("is kept beside it, then written back as version 22 with the queue in the order of its list, and lists nothing", async () => {
    // the list b, a: the queue starts at b, as before the upgrade
    const old = v21File([{ set: "teams/0/id", value: "b" }, { set: "teams/1/id", value: "a" }]);
    file.text = JSON.stringify(old, null, 2) + "\n";
    render(<App />);
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(file.old).toEqual([[21, file.text]]);
    const saved = JSON.parse(file.saved[0]);
    expect(saved).toEqual({ ...old, version: 22, team_queue: ["b", "a"], gift_lists: saved.gift_lists });
    expect(screen.queryByRole("region", { name: zh["moved.title"] })).toBeNull();
  });
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
