// The team queue (#501, #803): team_queue in settings.json is the queue the Agent rotates, and after a claim the Agent moves
// that team to its end. The team list is the user's to arrange: its drag and its ↑↓ leave the queue alone. A team added goes
// last in both, a team deleted leaves both. The editor takes the queue on disk, keeps the user's unsaved edits on top of it,
// and never saves its own stale queue over the Agent's.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT, fill } from "./i18n";
import { addTeam, movedToEnd, newSettings, newTeam, rebase, type Settings } from "./model";
import { applyEdits, cases, type Edit as FileEdit } from "./settingsCases";
import css from "./index.css?raw";
import { TeamsTab } from "./Teams";
import { cssValueOf, dragOnto, pickInList, renderEditor, sideList } from "./testing";

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
/** The rows of the team queue block (#804). */
const queueRows = () => within(screen.getByRole("group", { name: zh["queue.title"] })).getAllByRole("listitem");

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

describe("the team queue block above the list and the editor (#804)", () => {
  const rows = queueRows;
  /** Each row's text, as the user reads it. */
  const shown = () => rows().map((li) => li.querySelector(".item")!.textContent);

  test("lists every team in the queue's order, each with its place, name, in-game slot and usage", () => {
    const s = { ...queue("a", "b", "c"), team_queue: ["c", "a", "b"] };
    s.teams[1].game_team = 7;
    s.teams[1].usage = "normal_only";
    renderEditor(<TeamsTab />, s);
    expect(shown()).toEqual([
      expect.stringMatching(/^1\. Tc TEAMS #3/), expect.stringMatching(/^2\. Ta TEAMS #1/), expect.stringMatching(/^3\. Tb TEAMS #7/),
    ]);
    expect(rows().map((li) => [zh["usage.any"], zh["usage.normal_only"]].filter((u) => within(li).queryByText(u))))
      .toEqual([[zh["usage.any"]], [zh["usage.any"]], [zh["usage.normal_only"]]]); // 都可 too: the list shows only a kept one
  });

  test("a team that is off stays in its place, dimmed and tagged off", () => {
    const s = queue("a", "b", "c");
    s.teams[1].enabled = false;
    renderEditor(<TeamsTab />, s);
    const [a, b] = rows();
    expect(b).toHaveTextContent(`2. Tb`);
    expect(b).toHaveTextContent(zh["team.disabled"]);
    expect(a).not.toHaveTextContent(zh["team.disabled"]);
    expect(cssValueOf(css, b.querySelector(".item > span")!, "color")).toBe("var(--muted)");
    expect(cssValueOf(css, a.querySelector(".item > span")!, "color")).not.toBe("var(--muted)");
  });

  // The next run of each difficulty is the first enabled team in the queue whose usage fits it (agent/team_queue.py pick_team).
  /** The next-run marks, by row: "" for a row without one. */
  const marks = () => rows().map((li) => [zh["queue.next"], zh["queue.next_hard"], zh["queue.next_normal"]]
    .filter((m) => [...li.querySelectorAll("em")].some((em) => em.textContent === m)).join(" "));
  type Edit = Partial<Pick<Settings["teams"][number], "enabled" | "usage">>;
  test.each<[string, Edit[], string[]]>([
    ["one team plays both: one mark", [{ enabled: false }, {}, { usage: "hard_only" }], ["", zh["queue.next"], ""]],
    ["hard and normal play different teams: a mark each",
      [{ enabled: false, usage: "any" }, { usage: "hard_only" }, { usage: "any" }], ["", zh["queue.next_hard"], zh["queue.next_normal"]]],
    ["a team kept to Normal first, then one for both", [{ usage: "normal_only" }, {}, {}], [zh["queue.next_normal"], zh["queue.next_hard"], ""]],
    ["no team to play: no mark", [{ enabled: false }, { enabled: false }, { enabled: false }], ["", "", ""]],
    ["only Hard has a team: its mark says Hard", [{ usage: "hard_only" }, { enabled: false }, { usage: "hard_only" }], [zh["queue.next_hard"], "", ""]],
  ])("%s", (_, edits, expected) => {
    const s = { ...queue("a", "b", "c"), team_queue: ["c", "a", "b"] }; // the list's order is not the queue's
    const inQueue = s.team_queue.map((id) => s.teams.find((x) => x.id === id)!);
    edits.forEach((e, j) => Object.assign(inQueue[j], e));
    renderEditor(<TeamsTab />, s);
    expect(marks()).toEqual(expected);
  });

  // tests/settings_cases.json next_run: the agent's pick_team gives the same teams (tests/test_team_queue.py).
  test.each(cases.next_run as { name: string; edits: FileEdit[]; hard: string | null; normal: string | null }[])(
    "the marks name the teams the agent picks: $name", ({ edits, hard, normal }) => {
      const s = applyEdits(cases.valid, edits) as unknown as Settings;
      const mark = (id: string) => (hard === id && normal === id ? zh["queue.next"]
        : hard === id ? zh["queue.next_hard"] : normal === id ? zh["queue.next_normal"] : "");
      renderEditor(<TeamsTab />, s);
      expect(marks()).toEqual(s.team_queue.map(mark));
    });

  // The note sends the user to the Mirror Dungeon task's start team option (run.start_team, #805), which the settings
  // window's Run tab holds now, not a client's (#813, #814).
  test.each([
    ["zh_tw", "到「執行」分頁點鏡牢，用「這次從哪一支隊伍開始」"],
    ["en_us", "click Mirror Dungeon in the Run tab and use \"Start this task from team\""],
  ] as const)("its note in %s names the start team option of the Mirror Dungeon task in the Run tab", (lang, option) => {
    const note = TEXT[lang]["queue.note"];
    expect(note).toContain(option);
    expect(note).not.toMatch(/MXU|MFAAvalonia/);
  });

  test("its ↑↓ move a team in the queue, not in the list", async () => {
    const r = renderEditor(<TeamsTab />, queue("a", "b", "c"));
    await r.user.click(within(rows()[2]).getByRole("button", { name: zh.up }));
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c"], ["a", "c", "b"]]);
    await r.user.click(within(rows()[0]).getByRole("button", { name: zh.down }));
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c"], ["c", "a", "b"]]);
    expect(shown()).toEqual([expect.stringMatching(/^1\. Tc/), expect.stringMatching(/^2\. Ta/), expect.stringMatching(/^3\. Tb/)]);
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
    dragOnto(rows()[2], rows()[0]);
    expect(shown()).toEqual(["Tc", "Ta", "Tb"]);
    expect(document.querySelector(".status")).toHaveTextContent(zh.unsaved);
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect([ids(saved), saved.team_queue]).toEqual([["c", "a", "b"], ["a", "b", "c"]]);
  });

  describe("the queue block", () => {
    const rows = queueRows;
    const inBlock = () => rows().map((li) => li.textContent!.match(/T\w/)![0]);

    test("a drag and an ↑ in it save the queue in their order, and the team list as it was", async () => {
      const user = userEvent.setup();
      render(<App />);
      await waitFor(() => expect(inBlock()).toEqual(["Ta", "Tb", "Tc"]));
      dragOnto(rows()[2], rows()[0]);
      expect(inBlock()).toEqual(["Tc", "Ta", "Tb"]);
      await user.click(within(rows()[2]).getByRole("button", { name: zh.up }));
      expect(inBlock()).toEqual(["Tc", "Tb", "Ta"]);
      await user.click(screen.getByRole("button", { name: zh.save }));
      await waitFor(() => expect(file.saved).toHaveLength(1));
      const saved: Settings = JSON.parse(file.saved[0]);
      expect([saved.team_queue, ids(saved)]).toEqual([["c", "b", "a"], ["a", "b", "c"]]);
      expect(shown()).toEqual(["Ta", "Tb", "Tc"]);
    });

    test.each([
      ["the Agent moves a claimed team to the end", (s: Settings) => claimed(s, "a"), ["Tb", "Tc", "Ta"]],
      ["a task's start team is put first (#802)", (s: Settings) => ({ ...s, team_queue: ["c", "a", "b"] }), ["Tc", "Ta", "Tb"]],
    ])("shows the order the file has once the editor reads it again: %s", async (_, write, expected) => {
      render(<App />);
      await waitFor(() => expect(inBlock()).toEqual(["Ta", "Tb", "Tc"]));
      file.text = text(write(JSON.parse(file.text!)));
      act(() => { window.dispatchEvent(new Event("focus")); });
      await waitFor(() => expect(inBlock()).toEqual(expected));
      expect(shown()).toEqual(["Ta", "Tb", "Tc"]);
    });

    test("an unsaved move in it and the Agent's claim are both shown", async () => {
      const user = userEvent.setup();
      render(<App />);
      await waitFor(() => expect(inBlock()).toEqual(["Ta", "Tb", "Tc"]));
      await user.click(within(rows()[2]).getByRole("button", { name: zh.up })); // a, c, b
      agentClaims("a");
      act(() => { window.dispatchEvent(new Event("focus")); });
      await waitFor(() => expect(inBlock()).toEqual(["Tc", "Tb", "Ta"]));
    });

    test("an id of the queue that names no team is its own row, marked, and the problem's click focuses it", async () => {
      file.text = text({ ...queue("a", "b", "c"), team_queue: ["a", "b", "c", "x"] });
      const user = userEvent.setup();
      render(<App />);
      const extra = fill(zh["problem.queueExtra"], { name: "x" });
      await user.click(await within(await screen.findByRole("alert")).findByRole("button", { name: extra }));
      expect(rows()[3].querySelector(".item")).toHaveTextContent(/^4\. \? x$/);
      expect(within(rows()[3]).getByText(zh.hasProblem)).toBeInTheDocument();
      expect(document.activeElement).toBe(rows()[3].querySelector("[data-path='team_queue/3']"));
    });
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
    expect(screen.getByText(zh.saved)).toBeInTheDocument();
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
