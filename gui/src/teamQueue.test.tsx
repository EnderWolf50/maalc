// The team queue (#501, #803): team_queue in settings.json is the queue the Agent rotates, and after a claim the Agent moves
// that team to its end. The team list is the user's to arrange: its drag and its ↑↓ leave the queue alone. A team added goes
// last in both, a team deleted leaves both. The editor takes the queue on disk, keeps the user's unsaved edits on top of it,
// and never saves its own stale queue over the Agent's.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT } from "./i18n";
import { addTeam, movedToEnd, newSettings, newTeam, rebase, type Settings } from "./model";
import { cases } from "./settingsCases";
import { TeamsTab } from "./Teams";
import { pickInList, renderEditor, sideList } from "./testing";

// lib.rs save_settings: refused when the file is no longer the text the editor last read or wrote.
const file = vi.hoisted(() => ({ text: "" as string | null, saved: [] as string[], beforeSave: undefined as (() => void) | undefined }));
vi.mock("./api", async (original) => {
  const api = await original<typeof import("./api")>();
  return {
    ...api,
    loadSettings: () => Promise.resolve(file.text),
    saveSettings: async (text: string, expected: string | null) => {
      if (file.beforeSave) { // inside the IPC call's few ms, after React rendered what the caller set before it
        await new Promise((r) => setTimeout(r, 20));
        file.beforeSave();
        file.beforeSave = undefined;
        await new Promise((r) => setTimeout(r, 20));
      }
      if (expected !== file.text) throw api.CHANGED;
      file.saved.push(text);
      file.text = text;
    },
    rootDir: () => Promise.resolve("root"),
  };
});

const zh = TEXT.zh_tw;
/** Settings with teams of these ids, the list and the queue in this order. */
const queue = (...ids: string[]): Settings => {
  const s = { ...newSettings(), language: "zh_tw" as const };
  ids.forEach((id, n) => addTeam(s, { ...newTeam(n + 1, `T${id}`), id }));
  return s;
};
const ids = (s: Settings) => s.teams.map((t) => t.id);
const last = (order: string[], id: string) => [...order.filter((x) => x !== id), ...order.filter((x) => x === id)];
/** What the Agent writes after team `id` claimed: the same file, that team last in the queue (agent/team_queue.py requeue). */
const claimed = (s: Settings, id: string): Settings => ({ ...s, team_queue: last(s.team_queue, id) });
/** The same of a file the editor has not written back as version 22: its queue is the order of its teams. */
const claimedOld = (s: Settings, id: string): Settings => {
  const at = s.teams.findIndex((t) => t.id === id);
  return { ...s, teams: [...s.teams.slice(0, at), ...s.teams.slice(at + 1), s.teams[at]] };
};
const text = (s: Settings) => JSON.stringify(s, null, 2) + "\n";

describe("movedToEnd: the teams another writer moved to the end of the queue", () => {
  test.each([
    [["a", "b", "c"], ["b", "c", "a"], ["a"]], // the Agent after a's claim
    [["a", "b", "c"], ["a", "b", "c"], []],
    [["a", "b", "c", "d"], ["c", "d", "a", "b"], ["a", "b"]], // two claims, the old cursor's turn or a start team put first (c)
    [["a", "b"], ["a", "b", "n"], ["n"]], // a team added there
    [["a", "b", "c"], ["a", "c"], null], // a team deleted there: not a move
  ])("%j to %j", (before, after, moved) => {
    expect(movedToEnd(before, after)).toEqual(moved);
  });
});

describe("rebase: the editor's settings once another writer changed the file", () => {
  const base = queue("a", "b", "c");

  test("with no unsaved edit the editor takes the file as it is", () => {
    const disk = { ...claimed(base, "a"), language: "en_us" as const };
    expect(rebase(base, structuredClone(base), disk)).toEqual(disk);
  });

  test("an unsaved edit stays, with the queue the Agent wrote and the list as it was", () => {
    const draft = structuredClone(base);
    draft.teams[1].name = "renamed";
    const next = rebase(base, draft, claimed(base, "a"));
    expect([next.team_queue, ids(next)]).toEqual([["b", "c", "a"], ["a", "b", "c"]]);
    expect(next.teams[1].name).toBe("renamed");
  });

  test("an unsaved reorder of the list stays, and the queue takes the Agent's move", () => {
    const draft = { ...base, teams: [base.teams[2], base.teams[0], base.teams[1]] }; // c dragged to the top of the list
    const next = rebase(base, draft, claimed(base, "a"));
    expect([next.team_queue, ids(next)]).toEqual([["b", "c", "a"], ["c", "a", "b"]]);
  });

  test("an unsaved reorder of the queue stays, with the claimed team moved to the end of it", () => {
    const draft = { ...base, team_queue: ["c", "a", "b"] };
    expect(rebase(base, draft, claimed(base, "a")).team_queue).toEqual(["c", "b", "a"]);
  });

  test("a team added and a team deleted, unsaved, stay beside the Agent's move", () => {
    const draft = structuredClone(base);
    addTeam(draft, { ...newTeam(4, "Td"), id: "d" });
    draft.teams.splice(1, 1);
    draft.team_queue = draft.team_queue.filter((id) => id !== "b");
    const next = rebase(base, draft, claimed(base, "a"));
    expect([next.team_queue, ids(next)]).toEqual([["c", "d", "a"], ["a", "c", "d"]]);
  });

  test("a team the bot put first to start a task from (#802) is first under an unsaved edit too", () => {
    const draft = { ...base, teams: [base.teams[1], base.teams[0], base.teams[2]] }; // b dragged up in the list
    const next = rebase(base, draft, { ...base, team_queue: ["c", "a", "b"] });
    expect([next.team_queue, ids(next)]).toEqual([["c", "a", "b"], ["b", "a", "c"]]);
  });
});

describe("the team list and the queue in the teams tab", () => {
  /** The list a, b, c; the queue c, a, b. */
  const apart = () => ({ ...queue("a", "b", "c"), team_queue: ["c", "a", "b"] });
  const rows = () => sideList().getAllByRole("listitem");

  test("the list's ↑↓ move a team in the list, not in the queue", async () => {
    const r = renderEditor(<TeamsTab />, apart());
    await r.user.click(within(rows()[2]).getByRole("button", { name: zh.up }));
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "c", "b"], ["c", "a", "b"]]);
    await r.user.click(within(rows()[0]).getByRole("button", { name: zh.down }));
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["c", "a", "b"], ["c", "a", "b"]]);
  });

  test("a team added goes last in the list and last in the queue", async () => {
    const r = renderEditor(<TeamsTab />, apart());
    await r.user.click(screen.getByRole("button", { name: `+ ${zh.add}` }));
    const added = r.settings().teams[3].id;
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c", added], ["c", "a", "b", added]]);
  });

  test("a team deleted leaves both, and its Undo puts it back in its place in each", async () => {
    const r = renderEditor(<TeamsTab />, apart());
    await pickInList(r.user, "Tb");
    await r.user.click(screen.getByRole("button", { name: zh.remove }));
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "c"], ["c", "a"]]);
    await r.user.click(screen.getByRole("button", { name: zh.undo }));
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c"], ["c", "a", "b"]]);
  });

  test("the tab no longer says the list is the queue", () => {
    renderEditor(<TeamsTab />, apart());
    expect(document.body).not.toHaveTextContent("清單順序就是隊伍佇列");
  });
});

describe("in the editor", () => {
  beforeEach(() => { file.text = text(queue("a", "b", "c")); file.saved = []; file.beforeSave = undefined; });
  const shown = () => sideList().getAllByRole("listitem").map((li) => li.textContent!.match(/T\w/)![0]);
  const nameBox = () => screen.getByRole("textbox", { name: zh.name });
  const agentClaims = (id: string) => {
    const s = JSON.parse(file.text!);
    file.text = text(s.version < 22 ? claimedOld(s, id) : claimed(s, id));
  };

  // The drag the real window takes only in the foreground (docs/agents/gui-driving.md): the HTML5 events the list handles.
  test("dragging a team onto another in the list moves it there in the list; the saved queue stays", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
    const rows = () => sideList().getAllByRole("listitem");
    const dt = () => ({ setData() {}, effectAllowed: "", dropEffect: "" });
    fireEvent.dragStart(rows()[2], { dataTransfer: dt() });
    fireEvent.dragOver(rows()[0], { dataTransfer: dt() });
    fireEvent.drop(rows()[0], { dataTransfer: dt() });
    fireEvent.dragEnd(rows()[2], { dataTransfer: dt() });
    expect(shown()).toEqual(["Tc", "Ta", "Tb"]);
    expect(document.querySelector(".status")).toHaveTextContent(zh.unsaved);
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect([ids(saved), saved.team_queue]).toEqual([["c", "a", "b"], ["a", "b", "c"]]);
  });

  test("the queue the Agent wrote is taken when the window comes back to the front; the list keeps its order", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
    agentClaims("a");
    act(() => { window.dispatchEvent(new Event("focus")); });
    expect(await screen.findByText(zh.diskChanged)).toBeInTheDocument();
    expect(shown()).toEqual(["Ta", "Tb", "Tc"]);
    await user.type(nameBox(), "!");
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).team_queue).toEqual(["b", "c", "a"]);
  });

  test("the team being edited stays in the editor when the Agent moves it", async () => {
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    agentClaims("a");
    act(() => { window.dispatchEvent(new Event("focus")); });
    expect(await screen.findByText(zh.diskChanged)).toBeInTheDocument();
    expect(nameBox()).toHaveValue("Ta");
  });

  test("a save keeps the queue the Agent wrote under the unsaved edit", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    await user.type(nameBox(), "!");
    agentClaims("a"); // between two polls: the save itself finds it
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect([saved.teams.map((t) => t.name), saved.team_queue]).toEqual([["Ta!", "Tb", "Tc"], ["b", "c", "a"]]);
  });

  test("an unsaved drag of the list and the Agent's move of the queue are both in the save", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
    await user.click(within(sideList().getAllByRole("listitem")[2]).getByRole("button", { name: zh.up }));
    agentClaims("a");
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect([ids(saved), saved.team_queue]).toEqual([["a", "c", "b"], ["b", "c", "a"]]);
  });

  test("a poll and a save that read the Agent's write together save the Agent's queue", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    await user.type(nameBox(), "!");
    agentClaims("a");
    act(() => { // both syncs read the same file before React renders what the first one took
      window.dispatchEvent(new Event("focus"));
      screen.getByRole("button", { name: zh.save }).click();
    });
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).team_queue).toEqual(["b", "c", "a"]);
  });

  test("a save the Agent's write overtakes reads the file again and keeps that queue too", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    await user.type(nameBox(), "!");
    file.beforeSave = () => agentClaims("a"); // after the save read the file, before it writes
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect([saved.teams.map((t) => t.name), saved.team_queue]).toEqual([["Ta!", "Tb", "Tc"], ["b", "c", "a"]]);
    expect(screen.getByText(zh.savedTeams)).toBeInTheDocument(); // the rename changed the team list too (#780)
  });

  test("a file deleted while the editor is open is written again by a save", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    file.text = null;
    act(() => { window.dispatchEvent(new Event("focus")); });
    expect(await screen.findByText(zh.diskGone)).toBeInTheDocument();
    await user.type(nameBox(), "!");
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).teams[0].name).toBe("Ta!");
  });

  test("an old file the Agent reorders while the editor writes its migration back shows and keeps the Agent's order", async () => {
    const { team_queue: _, ...was } = JSON.parse(file.text!); // version 22 added it (#803)
    const old = { ...was, version: 20, ...cases.v20 }; // version 21 dropped these three sections (#782)
    file.text = text(old);
    file.beforeSave = () => { // the load's write-back meets the Agent's write, and a poll runs while it waits
      agentClaims("a");
      window.dispatchEvent(new Event("focus"));
    };
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    act(() => { window.dispatchEvent(new Event("focus")); });
    await waitFor(() => expect(shown()).toEqual(["Tb", "Tc", "Ta"]));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect([ids(saved), saved.team_queue]).toEqual([["b", "c", "a"], ["b", "c", "a"]]); // its queue was its list's order
  });

  test("a file put there while the editor had none is read", async () => {
    const put = file.text;
    file.text = null;
    render(<App />);
    expect(await screen.findByText(zh.noTeams)).toBeInTheDocument();
    file.text = put;
    act(() => { window.dispatchEvent(new Event("focus")); });
    await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
  });

  test("New file writes over a file that does not parse", async () => {
    file.text = "{";
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: zh.newFile }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
  });

  test("a save then a switch of language shows no stale saved note", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    await user.selectOptions(screen.getByRole("combobox", { name: zh.language }), "en_us");
    expect(document.querySelector(".status")).toHaveTextContent(/^Unsaved changes$/);
  });

  test("a file left half edited by hand is not saved over", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    file.text = "{";
    await user.type(nameBox(), "!");
    await user.click(screen.getByRole("button", { name: zh.save }));
    expect(await screen.findByText(zh.saveConflict, { exact: false })).toHaveTextContent(zh.unsaved);
    expect(file.saved).toEqual([]);
  });
});
