// The team queue (#501, #803, #954): team_queue in settings.json is the queue the Agent rotates, the teams the user put in it one
// by one, a team as often as wanted or not at all; after a claim the Agent moves that team's first place to its end. The team list
// is the user's to arrange: its drag and its Alt moves leave the queue alone, and a team added to it is not in the queue. A team
// deleted leaves both. The editor takes the queue on disk, keeps the user's unsaved edits on top of it, and never saves its own
// stale queue over the Agent's. The queue is shown and arranged in the Mirror Dungeon task's options on the Run tab (#878, spec
// #871 「隊伍佇列（只在鏡牢選項裡）」).
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App, { TABS } from "./App";
import { TEXT, fill } from "./i18n";
import { moveToEnd, movedToEnd, newSettings, newTeam, placeBack, queueWithTeam, rebase, type Settings } from "./model";
import { applyEdits, cases, type Edit as FileEdit } from "./settingsCases";
import css from "./index.css?raw";
import { TeamsTab } from "./Teams";
import { useEditor } from "./ui";
import { addQueued, altMove, cssValueOf, dragOnto, pickInList, renderEditor, sideList } from "./testing";

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
  ids.forEach((id, n) => addQueued(s, { ...newTeam(n + 1, `T${id}`), id }));
  return s;
};
const ids = (s: Settings) => s.teams.map((t) => t.id);
/** What the Agent writes after team `id` claimed: the same file, that team's first place last in the queue (agent/team_queue.py
 * requeue). */
const claimed = (s: Settings, id: string): Settings => {
  const at = s.team_queue.indexOf(id);
  return { ...s, team_queue: [...s.team_queue.slice(0, at), ...s.team_queue.slice(at + 1), id] };
};
/** The same of a file the editor has not written back as version 22: its queue is the order of its teams. */
const claimedOld = (s: Settings, id: string): Settings => {
  const at = s.teams.findIndex((t) => t.id === id);
  return { ...s, teams: [...s.teams.slice(0, at), ...s.teams.slice(at + 1), s.teams[at]] };
};
const text = (s: Settings) => JSON.stringify(s, null, 2) + "\n";
/** The team queue's frame, at the top of the Mirror Dungeon options (#878), and its rows. */
const queueFrame = () => screen.getByRole("group", { name: zh["queue.title"] });
const queueRows = () => within(queueFrame()).getAllByRole("listitem");
const RunTab = TABS.find((tab) => tab[0] === "run")![2];
/** Show the Mirror Dungeon task's options, as the user clicks its row in the task list. */
const showMirror = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(within(document.querySelector(".task-list")!).getByText(zh["task.MirrorDungeon"]));
/** The Run tab on these settings, the Mirror Dungeon task's options shown. */
async function mirror(s: Settings) {
  const r = renderEditor(<RunTab />, s);
  await showMirror(r.user);
  return r;
}
/** The buttons of the queue's place `n` (from 1), team `name`. */
const toTop = (n: number, name: string) => within(queueFrame()).getByRole("button", { name: fill(zh["queue.to_top_row"], { n, name }) });
const takeOut = (n: number, name: string) => within(queueFrame()).getByRole("button", { name: fill(zh["queue.remove_row"], { n, name }) });
const addButton = () => within(queueFrame()).getByRole("button", { name: zh["queue.add"] });
/** Add team `name` to the queue from 「加入隊伍」's menu. */
async function addFromMenu(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(addButton());
  await user.click(within(queueFrame()).getByRole("menuitem", { name: new RegExp(`^${name}`) }));
}

describe("movedToEnd: the teams another writer moved to the end of the queue", () => {
  test.each([
    [["a", "b", "c"], ["b", "c", "a"], ["a"]], // the Agent after a's claim
    [["a", "b", "c"], ["a", "b", "c"], []],
    [["a", "b", "c", "d"], ["c", "d", "a", "b"], ["a", "b"]], // two claims, or the old cursor's turn
    [["a", "a", "b"], ["a", "b", "a"], ["a"]], // a's first place (#954)
    [["a", "a", "b"], ["b", "a", "a"], ["a", "a"]], // both of them, two claims
    [["a", "a", "b"], ["a", "a", "b"], []], // three claims: round to where it was
    [["a", "b", "a"], ["b", "a", "a"], ["a"]],
    [["b", "b", "a", "a"], ["b", "b", "a", "a"], []], // b passed over, a's claim moves its first place behind its second
    [["b", "a", "b", "a"], ["b", "b", "a", "a"], ["a"]], // b passed over, its places stay
    [["a", "b"], ["a", "b", "n"], null], // a place added there: not a move
    [["a", "b"], ["a", "b", "a"], null], // the same, of a team it has
    [["a", "b", "c"], ["a", "c"], null], // a team deleted there
    [["a", "a", "b"], ["a", "b"], null], // a place taken out there
    [["a", "b"], ["a", "c"], null], // another team there
    [[], [], []],
  ])("%j to %j", (before, after, moved) => {
    expect(movedToEnd(before, after)).toEqual(moved);
  });
});

describe("queueWithTeam: the queue once a deleted team's Undo puts its places back (#954)", () => {
  test.each([
    ["as it was, nothing moved since", ["b", "a", "b"], ["a"], ["b", "a", "b"]],
    ["the Agent's move since is made in it too", ["a", "b", "c", "b"], ["c", "a"], ["b", "c", "b", "a"]],
    ["no place before, none after", ["a", "c"], ["c", "a"], ["c", "a"]],
    ["a place added since stays; each place back at its old index", ["b", "a", "b"], ["a", "n"], ["b", "a", "b", "n"]],
    ["the queue emptied since: each place back", ["a", "b", "b"], [], ["b", "b"]],
  ])("%s", (_, was, now, after) => {
    expect(queueWithTeam(was, now, "b")).toEqual(after);
  });
});

describe("placeBack: where a place taken out goes back (#954)", () => {
  test.each<[string, string[], number, string[], number]>([
    ["nothing moved since: its old place", ["a", "b", "c"], 1, ["a", "c"], 1],
    ["the Agent moved the one before it: one up", ["a", "b", "c"], 1, ["c", "a"], 0],
    ["the Agent moved one after it: its old place", ["a", "b", "c", "d"], 1, ["a", "d", "c"], 1],
    ["the last place, after a move: before the one moved", ["a", "b", "c"], 2, ["b", "a"], 1],
    ["a team's first place, its other one moved since", ["a", "b", "a", "c"], 0, ["b", "c", "a"], 1],
    ["a place added since: its old place", ["a", "b", "c"], 1, ["c", "a", "n"], 1],
  ])("%s", (_, was, at, now, place) => {
    expect(placeBack(was, at, now)).toBe(place);
  });
});

test("moveToEnd moves an id's first place, and an id the queue lacks moves nothing (#954)", () => {
  expect(moveToEnd(["a", "b", "a"], ["a", "x", "b"])).toEqual(["a", "a", "b"]);
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
    addQueued(draft, { ...newTeam(4, "Td"), id: "d" });
    draft.teams.splice(1, 1);
    draft.team_queue = draft.team_queue.filter((id) => id !== "b");
    const next = rebase(base, draft, claimed(base, "a"));
    expect([next.team_queue, ids(next)]).toEqual([["c", "d", "a"], ["a", "c", "d"]]);
  });

  describe("a team with several places (#954)", () => {
    const twice = { ...base, team_queue: ["a", "a", "b"] };

    test("a claim moves one of its places, not both", () => {
      const draft = structuredClone(twice);
      draft.teams[1].name = "renamed";
      expect(rebase(twice, draft, claimed(twice, "a")).team_queue).toEqual(["a", "b", "a"]);
      expect(rebase(twice, draft, claimed(claimed(twice, "a"), "a")).team_queue).toEqual(["b", "a", "a"]);
      expect(rebase(twice, draft, claimed(claimed(claimed(twice, "a"), "a"), "b")).team_queue).toEqual(["a", "a", "b"]);
    });

    test("an unsaved add, of the same team too, stays beside the claim", () => {
      expect(rebase(twice, { ...twice, team_queue: ["a", "a", "b", "a", "c"] }, claimed(twice, "a")).team_queue)
        .toEqual(["a", "b", "a", "c", "a"]);
    });

    test("an unsaved place taken out stays out; with another place left the claim moves that one, with none it moves nothing", () => {
      expect(rebase(twice, { ...twice, team_queue: ["a", "b"] }, claimed(twice, "a")).team_queue).toEqual(["b", "a"]);
      expect(rebase(twice, { ...twice, team_queue: ["b"] }, claimed(twice, "a")).team_queue).toEqual(["b"]);
      expect(rebase(twice, { ...twice, team_queue: [] }, claimed(twice, "a")).team_queue).toEqual([]);
    });

    test("a file whose queue gained or lost a place moves nothing in the edits", () => {
      const draft = { ...twice, team_queue: ["b", "a", "a"] };
      expect(rebase(twice, draft, { ...twice, team_queue: ["a", "b"] }).team_queue).toEqual(["b", "a", "a"]);
      expect(rebase(twice, draft, { ...twice, team_queue: ["a", "a", "b", "b"] }).team_queue).toEqual(["b", "a", "a"]);
    });
  });
});

describe("the team list and the queue in the teams tab", () => {
  /** The list a, b, c; the queue c, a, b. */
  const apart = () => ({ ...queue("a", "b", "c"), team_queue: ["c", "a", "b"] });
  const rows = () => sideList().getAllByRole("listitem");

  test("Alt with an arrow in the list moves a team in the list, not in the queue", async () => {
    const r = renderEditor(<TeamsTab />, apart());
    await altMove(r.user, rows()[2], "ArrowUp");
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "c", "b"], ["c", "a", "b"]]);
    await altMove(r.user, rows()[0], "ArrowDown");
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["c", "a", "b"], ["c", "a", "b"]]);
  });

  test("a team added goes last in the list, and not into the queue (#954)", async () => {
    const r = renderEditor(<TeamsTab />, apart());
    await r.user.click(screen.getByRole("button", { name: `+ ${zh.add}` }));
    const added = r.settings().teams[3].id;
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c", added], ["c", "a", "b"]]);
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

  test("the tab has no queue; a line under the list says where the queue is arranged (#878)", () => {
    renderEditor(<TeamsTab />, apart());
    expect(screen.queryByRole("group", { name: zh["queue.title"] })).toBeNull();
    expect(screen.queryByRole("list", { name: zh["queue.title"] })).toBeNull();
    const note = sideList().getByText(zh["teams.order_note"]);
    expect(note).toBeVisible();
    expect(zh["teams.order_note"]).toBe("清單順序只是顯示用。隊伍要自己加進佇列才會打鏡牢：在「執行」分頁點鏡牢，按「隊伍佇列」的「加入隊伍」。");
    expect(cssValueOf(css, note, "font-size")).toBe("12.5px");
  });
});

describe("the team queue at the top of the Mirror Dungeon options (#878)", () => {
  const rows = queueRows;
  /** Each row's text, as the user reads it: place, name, slot, usage, the next-run mark. */
  const shown = () => rows().map((li) => li.textContent!.replace(/\s+/g, " ").trim());

  test("is the options' first frame, the groups under it; the other tasks show none", async () => {
    const r = await mirror(queue("a", "b", "c"));
    const titles = [...document.querySelectorAll(".task-options fieldset > legend")].map((x) => x.textContent);
    expect(titles).toEqual([zh["queue.title"], zh["run.group_run"], zh["run.group_weekly"], zh["run.group_failure"]]);
    expect(cssValueOf(css, queueFrame(), "grid-column")).toBe("1 / -1"); // the box's whole width
    await r.user.click(within(document.querySelector(".task-list")!).getByText("經驗本"));
    expect(screen.queryByRole("group", { name: zh["queue.title"] })).toBeNull();
  });

  test("lists the queue in its order: each place's number, name and slot, and its usage only when kept to one difficulty", async () => {
    const s = { ...queue("a", "b", "c"), team_queue: ["c", "a", "b"] };
    s.teams[1].game_team = 17;
    s.teams[1].usage = "normal_only";
    s.teams[2].usage = "hard_only";
    await mirror(s);
    expect(screen.getByRole("list", { name: zh["queue.title"] })).toBe(rows()[0].parentElement);
    expect(shown()).toEqual([
      expect.stringMatching(/^1 Tc TEAMS #3 只跑困難/), expect.stringMatching(/^2 Ta TEAMS #1(?! 只跑| 都可)/), "3 Tb TEAMS #17 只跑普通",
    ]);
    expect(queueFrame()).not.toHaveTextContent(zh["usage.any"]);
    // the slot, the usage, the mark and the buttons in columns every row shares (subgrid), the slot's numerals of one width
    expect(cssValueOf(css, rows()[0], "grid-template-columns")).toBe("subgrid");
    expect(cssValueOf(css, within(rows()[2]).getByText("TEAMS #17"), "font-variant-numeric")).toBe("tabular-nums");
  });

  test("a long name is cut short with an ellipsis rather than move the columns", async () => {
    const s = queue("a");
    s.teams[0].name = "名字很長很長很長很長很長很長的隊伍";
    await mirror(s);
    const name = within(rows()[0]).getByText(s.teams[0].name);
    expect(["text-overflow", "white-space", "overflow"].map((p) => cssValueOf(css, name, p))).toEqual(["ellipsis", "nowrap", "hidden"]);
  });

  // The next new run of each difficulty the task plays (run.difficulty; auto plays either) is the first team in the queue whose
  // usage fits it (agent/team_queue.py pick_team).
  /** The next-run mark of each row: "" for none, 下一局 alone, or with the difficulty's plate. */
  const marks = () => rows().map((li) => li.textContent!.match(new RegExp(`${zh["queue.next"]}(${zh["difficulty.normal"]}|${zh["difficulty.hard"]})?`))?.[0] ?? "");
  const NEXT = zh["queue.next"], NORMAL = NEXT + zh["difficulty.normal"], HARD = NEXT + zh["difficulty.hard"];
  type Usage = "any" | "hard_only" | "normal_only";
  test.each<[string, string[], Record<string, Usage>, Partial<Settings["run"]>, string[]]>([
    ["one team plays both: 下一局 alone", ["c", "a", "b"], { b: "hard_only" }, {}, [NEXT, "", ""]],
    ["hard and normal play different teams: 下一局 with each one's plate", ["a", "b"], { a: "hard_only" }, {}, [HARD, NORMAL]],
    ["a team kept to Normal first, then one for both", ["c", "a", "b"], { c: "normal_only" }, {}, [NORMAL, HARD, ""]],
    ["a team twice: its first place alone is marked", ["a", "a", "b"], {}, {}, [NEXT, "", ""]],
    ["a team twice, after one kept to Hard twice", ["b", "b", "a", "a"], { b: "hard_only" }, {}, [HARD, "", NORMAL, ""]],
    ["only Hard has a team: its mark says Hard", ["c", "b"], { c: "hard_only", b: "hard_only" }, {}, [HARD, ""]],
    ["the task plays Hard only: Hard's team alone, no plate", ["c", "a"], { c: "normal_only" }, { difficulty: "hard" }, ["", NEXT]],
    ["the task plays Normal only: Normal's team alone, no plate", ["c", "a"], { c: "hard_only" }, { difficulty: "normal" }, ["", NEXT]],
    ["no team for the task's difficulty: no mark", ["c", "c"], { c: "hard_only" }, { difficulty: "normal" }, ["", ""]],
  ])("%s", async (_, order, usage, run, expected) => {
    const s = { ...queue("a", "b", "c"), team_queue: order };
    for (const team of s.teams) team.usage = usage[team.id] ?? "any";
    Object.assign(s.run, run);
    await mirror(s);
    expect(marks()).toEqual(expected);
  });

  test("the mark is the amber words, its plate after them; Hard's plate filled, Normal's a frame, neither red", async () => {
    const s = queue("a", "b");
    s.teams[0].usage = "hard_only";
    await mirror(s);
    const [hard, normal] = rows().map((li) => within(li).getByText(new RegExp(`^${NEXT}`)));
    expect(cssValueOf(css, hard, "color")).toBe("var(--accent-ink)");
    const plate = (mark: HTMLElement, d: string) => within(mark).getByText(zh[`difficulty.${d}` as keyof typeof zh]);
    expect(cssValueOf(css, plate(hard, "hard"), "background")).toBe("var(--line)");
    expect(cssValueOf(css, plate(normal, "normal"), "background")).toBeUndefined();
    expect(cssValueOf(css, plate(normal, "normal"), "border")).toMatch(/solid/);
    for (const [mark, d] of [[hard, "hard"], [normal, "normal"]] as const) {
      expect([cssValueOf(css, plate(mark, d), "color"), cssValueOf(css, plate(mark, d), "background")].join()).not.toMatch(/bad/);
    }
  });

  // tests/settings_cases.json next_run: the agent's pick_team gives the same teams (tests/test_team_queue.py).
  test.each(cases.next_run as { name: string; edits: FileEdit[]; hard: string | null; normal: string | null }[])(
    "the marks name the teams the agent picks: $name", async ({ edits, hard, normal }) => {
      const s = applyEdits(cases.valid, edits) as unknown as Settings;
      const mark = (id: string) => (hard === id && normal === id ? NEXT : hard === id ? HARD : normal === id ? NORMAL : "");
      await mirror(s);
      if (s.team_queue.length) expect(marks()).toEqual(s.team_queue.map((id, j) => (s.team_queue.indexOf(id) === j ? mark(id) : "")));
      else expect(queueFrame()).not.toHaveTextContent(NEXT);
    });

  test("Alt with an arrow in it moves a team in the queue, not in the list", async () => {
    const r = await mirror(queue("a", "b", "c"));
    await altMove(r.user, rows()[2], "ArrowUp");
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c"], ["a", "c", "b"]]);
    await altMove(r.user, rows()[0], "ArrowDown");
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c"], ["c", "a", "b"]]);
    expect(shown()).toEqual([expect.stringMatching(/^1 Tc/), expect.stringMatching(/^2 Ta/), expect.stringMatching(/^3 Tb/)]);
  });

  test("no start team: no flag and no 這次從哪一支隊伍開始 pick (#954)", async () => {
    await mirror(queue("a", "b"));
    expect(within(queueFrame()).queryByRole("button", { pressed: true })).toBeNull();
    for (const gone of ["起頭", "旗子", "這次從", "停用"]) expect(document.body.innerHTML).not.toContain(gone);
  });
});

describe("the queue put together one team at a time (#954)", () => {
  const shownNames = () => queueRows().map((li) => li.textContent!.match(/T\w/)![0]);

  test("「加入隊伍」 under the queue lists every team with its slot and how often the queue has it; a pick adds it at the end", async () => {
    const s = queue("a", "b", "c");
    s.teams[1].game_team = 17;
    s.team_queue = ["b", "a", "b"];
    const r = await mirror(s);
    expect(queueFrame().querySelector("ol")!.compareDocumentPosition(addButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(addButton()).toHaveAttribute("aria-haspopup", "menu");
    await r.user.click(addButton());
    const items = within(queueFrame()).getAllByRole("menuitem").map((x) => [...x.children].map((c) => c.textContent));
    expect(items).toEqual([["Ta", "TEAMS #1 · 已排 1 次"], ["Tb", "TEAMS #17 · 已排 2 次"], ["Tc", "TEAMS #3"]]); // the list's order
    await r.user.click(within(queueFrame()).getByRole("menuitem", { name: /^Tc/ }));
    expect(r.settings().team_queue).toEqual(["b", "a", "b", "c"]);
    expect(ids(r.settings())).toEqual(["a", "b", "c"]);
    expect(within(queueFrame()).queryByRole("menu")).toBeNull();
    expect(addButton()).toHaveFocus();
  });

  test("the same team may be added over and over, each a row of its own", async () => {
    const r = await mirror({ ...queue("a", "b"), team_queue: [] });
    for (const name of ["Ta", "Ta", "Tb", "Ta"]) await addFromMenu(r.user, name);
    expect(r.settings().team_queue).toEqual(["a", "a", "b", "a"]);
    expect(shownNames()).toEqual(["Ta", "Ta", "Tb", "Ta"]);
    expect(queueRows().map((li) => li.querySelector(".place")!.textContent)).toEqual(["1", "2", "3", "4"]);
  });

  test("the menu by keyboard: the arrows go round, Enter adds, Escape closes to the button", async () => {
    const r = await mirror({ ...queue("a", "b"), team_queue: ["a"] });
    addButton().focus();
    await r.user.keyboard("{Enter}{ArrowUp}");
    expect(within(queueFrame()).getByRole("menuitem", { name: /^Tb/ })).toHaveFocus();
    await r.user.keyboard("{Escape}");
    expect(within(queueFrame()).queryByRole("menu")).toBeNull();
    expect(addButton()).toHaveFocus();
    await r.user.keyboard("{Enter}{ArrowDown}{Enter}");
    expect(r.settings().team_queue).toEqual(["a", "b"]);
  });

  test("✕ takes out its own place alone, whichever of a team's it is; the Undo puts that place back, its words not a delete's", async () => {
    const r = await mirror({ ...queue("a", "b"), team_queue: ["a", "b", "a"] });
    await r.user.click(takeOut(1, "Ta"));
    expect(r.settings().team_queue).toEqual(["b", "a"]);
    expect(queueRows()[0]).toHaveFocus(); // the row that took its place
    expect(within(queueFrame()).getByRole("status")).toHaveTextContent("已把「Ta」移出佇列。");
    expect(ids(r.settings())).toEqual(["a", "b"]); // the team itself stays
    await r.user.click(within(queueFrame()).getByRole("button", { name: zh.undo }));
    expect(r.settings().team_queue).toEqual(["a", "b", "a"]);
    expect(queueRows()[0]).toHaveFocus();
    await r.user.click(takeOut(3, "Ta"));
    expect(r.settings().team_queue).toEqual(["a", "b"]);
    await r.user.click(within(queueFrame()).getByRole("button", { name: zh.undo }));
    expect(r.settings().team_queue).toEqual(["a", "b", "a"]);
    expect(queueRows()[2]).toHaveFocus();
    expect(within(queueFrame()).queryByRole("button", { name: zh.undo })).toBeNull();
  });

  test("a claim between the ✕ and its Undo: the place goes back with that move made, as if it had never left", async () => {
    function Claim() { // what the editor holds once the Agent's requeue of a is read
      const { update } = useEditor();
      return <button onClick={() => update((s) => { s.team_queue = moveToEnd(s.team_queue, ["a"]); })}>claim a</button>;
    }
    const r = renderEditor(<><RunTab /><Claim /></>, queue("a", "b", "c"));
    await showMirror(r.user);
    await r.user.click(takeOut(2, "Tb"));
    await r.user.click(screen.getByRole("button", { name: "claim a" }));
    expect(r.settings().team_queue).toEqual(["c", "a"]);
    await r.user.click(within(queueFrame()).getByRole("button", { name: zh.undo }));
    expect(r.settings().team_queue).toEqual(["b", "c", "a"]);
    expect(queueRows()[0]).toHaveFocus();
  });

  test("the user's own move or add between the ✕ and its Undo: the place goes back to its old number", async () => {
    const r = await mirror(queue("a", "b", "c", "d"));
    await r.user.click(takeOut(2, "Tb"));
    await r.user.click(toTop(3, "Td")); // d, a, c
    await r.user.click(within(queueFrame()).getByRole("button", { name: zh.undo }));
    expect(r.settings().team_queue).toEqual(["d", "b", "a", "c"]);
    await r.user.click(takeOut(1, "Td"));
    await addFromMenu(r.user, "Ta"); // b, a, c, a
    await r.user.click(within(queueFrame()).getByRole("button", { name: zh.undo }));
    expect(r.settings().team_queue).toEqual(["d", "b", "a", "c", "a"]);
  });

  test("the last place taken out leaves the add button the focus, and its Undo brings the queue back", async () => {
    const r = await mirror({ ...queue("a"), team_queue: ["a"] });
    await r.user.click(takeOut(1, "Ta"));
    expect(r.settings().team_queue).toEqual([]);
    expect(addButton()).toHaveFocus();
    await r.user.click(within(queueFrame()).getByRole("button", { name: zh.undo }));
    expect(r.settings().team_queue).toEqual(["a"]);
  });

  test("「排到最上面」 moves its place to the top, the rest in their order, once: nothing else is kept in the settings", async () => {
    const s = { ...queue("a", "b", "c"), team_queue: ["a", "b", "a", "c"] };
    const r = await mirror(s);
    await r.user.click(toTop(4, "Tc"));
    expect(r.settings()).toEqual({ ...s, team_queue: ["c", "a", "b", "a"] });
    expect(queueRows()[0]).toHaveFocus(); // the moved row, as an Alt move's
    await r.user.click(toTop(4, "Ta"));
    expect(r.settings().team_queue).toEqual(["a", "c", "a", "b"]);
  });

  test("the top row's 「排到最上面」 is off, the others' on; both buttons say what they do", async () => {
    await mirror({ ...queue("a", "b"), team_queue: ["a", "a", "b"] });
    expect(toTop(1, "Ta")).toBeDisabled();
    expect([toTop(2, "Ta"), toTop(3, "Tb")].map((b) => (b as HTMLButtonElement).disabled)).toEqual([false, false]);
    expect(toTop(2, "Ta")).toHaveAttribute("title", "排到最上面");
    expect(takeOut(1, "Ta")).toBeEnabled();
    expect(takeOut(1, "Ta")).toHaveAttribute("title", "移出佇列");
    expect([zh["queue.to_top_row"], zh["queue.remove_row"]]).toEqual(["把第 {n} 位「{name}」排到最上面", "把第 {n} 位「{name}」移出佇列"]);
  });

  test("a drag moves the place it takes, of a team with several", async () => {
    const r = await mirror({ ...queue("a", "b"), team_queue: ["a", "a", "b"] });
    dragOnto(queueRows()[2], queueRows()[1]);
    expect(r.settings().team_queue).toEqual(["a", "b", "a"]);
    dragOnto(queueRows()[0], queueRows()[2]);
    expect(r.settings().team_queue).toEqual(["b", "a", "a"]);
  });

  test("Alt with an arrow moves a place past another of the same team, and the moved row keeps the focus", async () => {
    const r = await mirror({ ...queue("a", "b"), team_queue: ["a", "a", "b"] });
    await altMove(r.user, queueRows()[2], "Home");
    expect(r.settings().team_queue).toEqual(["b", "a", "a"]);
    expect(queueRows()[0]).toHaveFocus();
    await altMove(r.user, queueRows()[1], "ArrowDown"); // the two places of a: the same queue
    expect(r.settings().team_queue).toEqual(["b", "a", "a"]);
    expect(queueRows()[2]).toHaveFocus();
  });

  test("an empty queue says Mirror Dungeon plays no run, and how to add a team", async () => {
    await mirror({ ...queue("a"), team_queue: [] });
    expect(within(queueFrame()).queryByRole("list")).toBeNull();
    expect(within(queueFrame()).getByText(zh["queue.empty"])).toBeVisible();
    expect(zh["queue.empty"]).toBe("佇列是空的：鏡牢不會打，任務直接結束。按「加入隊伍」加進來。");
    expect(addButton()).toBeEnabled();
  });

  test("with no team at all the add button is off, and the words send the user to the Teams tab", async () => {
    await mirror(queue());
    expect(within(queueFrame()).getByText(zh["queue.empty_no_teams"])).toBeVisible();
    expect(zh["queue.empty_no_teams"]).toContain("「隊伍」分頁");
    expect(addButton()).toBeDisabled();
  });

  test("an id that names no team is taken out by its ✕", async () => {
    const r = await mirror({ ...queue("a"), team_queue: ["a", "x"] });
    await r.user.click(takeOut(2, "? x"));
    expect(r.settings().team_queue).toEqual(["a"]);
  });

  test("in English too", async () => {
    const en = TEXT.en_us;
    renderEditor(<RunTab />, { ...queue("a"), language: "en_us", team_queue: ["a"] });
    await userEvent.setup().click(within(document.querySelector(".task-list")!).getByText(en["task.MirrorDungeon"]));
    const frame = within(screen.getByRole("group", { name: en["queue.title"] }));
    expect(frame.getByRole("button", { name: "Move place 1, Ta, to the top" })).toBeDisabled();
    await userEvent.setup().click(frame.getByRole("button", { name: "Add a team" }));
    expect(frame.getByRole("menuitem")).toHaveTextContent("TEAMS #1 · in the queue: 1");
    await userEvent.setup().click(frame.getByRole("button", { name: "Take place 1, Ta, out of the queue" }));
    expect(frame.getByText(en["queue.empty"])).toBeVisible();
    expect(frame.getByRole("status")).toHaveTextContent("Took “Ta” out of the queue.");
  });
});
// Locked during a run: runner.test.tsx 「during a run」 (a run of the real page's runner sets the lock).

describe("the next run on the task list's Mirror Dungeon row (#878)", () => {
  const taskRows = () => within(document.querySelector(".task-list")!).getAllByRole("listitem");
  const mirrorRows = () => taskRows().filter((li) => within(li).queryByText(zh["task.MirrorDungeon"]));
  /** The next-run line of a row, or null. */
  const nextLine = (li: HTMLElement) => within(li).queryByText(zh["queue.next"])?.parentElement ?? null;

  test("its second line names the next run's team; two teams, each after its plate, 普通 first", async () => {
    const s = queue("a", "b");
    s.teams[0].usage = "hard_only";
    s.team_queue = ["a", "b"];
    renderEditor(<RunTab />, s);
    const line = nextLine(mirrorRows()[0])!;
    expect(line).toHaveTextContent(new RegExp(`^${zh["queue.next"]}\\s*${zh["difficulty.normal"]}\\s*Tb\\s*${zh["difficulty.hard"]}\\s*Ta$`));
    expect(line).not.toHaveAttribute("aria-hidden");
  });

  test("one team for every difficulty: its name alone; none: says so", async () => {
    renderEditor(<RunTab />, queue("a", "b"));
    expect(nextLine(mirrorRows()[0])).toHaveTextContent(new RegExp(`^${zh["queue.next"]}\\s*Ta$`));
    cleanup();
    const s = queue("a");
    s.teams[0].usage = "hard_only";
    s.run.difficulty = "normal";
    renderEditor(<RunTab />, s);
    expect(nextLine(mirrorRows()[0])).toHaveTextContent(new RegExp(`^${zh["queue.next"]}\\s*${zh["queue.no_team"]}$`));
  });

  test("an empty queue: the row says it plays none (#954)", async () => {
    renderEditor(<RunTab />, { ...queue("a"), team_queue: [] });
    expect(nextLine(mirrorRows()[0])).toHaveTextContent(new RegExp(`^${zh["queue.next"]}\\s*${zh["queue.empty_next"]}$`));
    expect(zh["queue.empty_next"]).toBe("佇列是空的，不會打");
  });

  test("only on the first ticked Mirror Dungeon row; none while none is ticked", async () => {
    const s = queue("a");
    s.tasks = [{ id: "MirrorDungeon", enabled: false }, { id: "ClaimMail", enabled: true }, { id: "MirrorDungeon", enabled: true },
      { id: "MirrorDungeon", enabled: true }];
    const r = renderEditor(<RunTab />, s);
    const nth = (n: number) => screen.getByRole("checkbox", { name: fill(zh["tasks.tick_nth"], { name: zh["task.MirrorDungeon"], n }) });
    expect(mirrorRows().map((li) => nextLine(li) !== null)).toEqual([false, true, false]);
    await r.user.click(nth(2));
    expect(mirrorRows().map((li) => nextLine(li) !== null)).toEqual([false, false, true]);
    await r.user.click(nth(3));
    expect(mirrorRows().map((li) => nextLine(li) !== null)).toEqual([false, false, false]);
  });

  test("one line: where the names do not fit it leaves the row, hidden from a screen reader too, and the row keeps one line's height", async () => {
    // a layout where the line holds more than it shows: jsdom lays nothing out, so these two shadow Element's zeroes awhile
    const isLine = (el: HTMLElement) => el.firstElementChild?.textContent === zh["queue.next"];
    Object.defineProperty(HTMLElement.prototype, "scrollWidth", { configurable: true, get() { return isLine(this) ? 300 : 0; } });
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get() { return isLine(this) ? 200 : 0; } });
    try {
      renderEditor(<RunTab />, queue("a"));
      const line = nextLine(mirrorRows()[0])!;
      expect(line).toHaveAttribute("aria-hidden", "true");
      expect(cssValueOf(css, line, "visibility")).toBe("hidden");
      expect(cssValueOf(css, line, "position")).toBe("absolute"); // out of the row's flow: the row is one line high
      expect(cssValueOf(css, line, "white-space")).toBe("nowrap");
    } finally {
      Reflect.deleteProperty(HTMLElement.prototype, "scrollWidth");
      Reflect.deleteProperty(HTMLElement.prototype, "clientWidth");
    }
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
    render(<App start="teams" />);
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

  describe("the queue in the Mirror Dungeon options", () => {
    const rows = queueRows;
    const inQueue = () => rows().map((li) => li.textContent!.match(/T\w/)![0]);
    /** The window on its Run tab, the Mirror Dungeon task's options shown once the settings are read. */
    async function openMirror() {
      const user = userEvent.setup();
      render(<App />);
      await screen.findByText(zh["task.MirrorDungeon"]);
      await showMirror(user);
      return user;
    }
    const toTeams = async (user: ReturnType<typeof userEvent.setup>) => {
      await user.click(screen.getByRole("tab", { name: zh["tab.teams"] }));
      await waitFor(() => expect(shown()).toHaveLength(3));
    };

    test("a drag and an Alt+↑ in it save the queue in their order, and the team list as it was", async () => {
      const user = await openMirror();
      await waitFor(() => expect(inQueue()).toEqual(["Ta", "Tb", "Tc"]));
      dragOnto(rows()[2], rows()[0]);
      expect(inQueue()).toEqual(["Tc", "Ta", "Tb"]);
      await altMove(user, rows()[2], "ArrowUp");
      expect(inQueue()).toEqual(["Tc", "Tb", "Ta"]);
      await user.click(screen.getByRole("button", { name: zh.save }));
      await waitFor(() => expect(file.saved).toHaveLength(1));
      const saved: Settings = JSON.parse(file.saved[0]);
      expect([saved.team_queue, ids(saved)]).toEqual([["c", "b", "a"], ["a", "b", "c"]]);
      await toTeams(user);
      expect(shown()).toEqual(["Ta", "Tb", "Tc"]);
    });

    test("teams added, put on top and taken out save the queue as shown, and the team list as it was (#954)", async () => {
      const user = await openMirror();
      await waitFor(() => expect(inQueue()).toEqual(["Ta", "Tb", "Tc"]));
      await addFromMenu(user, "Ta");
      await user.click(takeOut(3, "Tc"));
      await user.click(toTop(2, "Tb"));
      expect(inQueue()).toEqual(["Tb", "Ta", "Ta"]);
      await user.click(screen.getByRole("button", { name: zh.save }));
      await waitFor(() => expect(file.saved).toHaveLength(1));
      const saved: Settings = JSON.parse(file.saved[0]);
      expect([saved.team_queue, ids(saved)]).toEqual([["b", "a", "a"], ["a", "b", "c"]]);
    });

    test.each([
      ["the Agent moves a claimed team to the end", (s: Settings) => claimed(s, "a"), ["Tb", "Tc", "Ta"]],
      ["another writer put a team in twice (#954)", (s: Settings) => ({ ...s, team_queue: ["c", "a", "c"] }), ["Tc", "Ta", "Tc"]],
    ])("shows the order the file has once the editor reads it again: %s", async (_, write, expected) => {
      const user = await openMirror();
      await waitFor(() => expect(inQueue()).toEqual(["Ta", "Tb", "Tc"]));
      file.text = text(write(JSON.parse(file.text!)));
      act(() => { window.dispatchEvent(new Event("focus")); });
      await waitFor(() => expect(inQueue()).toEqual(expected));
      await toTeams(user);
      expect(shown()).toEqual(["Ta", "Tb", "Tc"]);
    });

    test("an unsaved move in it and the Agent's claim are both shown", async () => {
      const user = await openMirror();
      await waitFor(() => expect(inQueue()).toEqual(["Ta", "Tb", "Tc"]));
      await altMove(user, rows()[2], "ArrowUp"); // a, c, b
      agentClaims("a");
      act(() => { window.dispatchEvent(new Event("focus")); });
      await waitFor(() => expect(inQueue()).toEqual(["Tc", "Tb", "Ta"]));
    });

    test("an unsaved add and the Agent's claim of a team with two places are both shown and saved (#954)", async () => {
      file.text = text({ ...queue("a", "b", "c"), team_queue: ["a", "a", "b"] });
      const user = await openMirror();
      await waitFor(() => expect(inQueue()).toEqual(["Ta", "Ta", "Tb"]));
      await addFromMenu(user, "Tc");
      agentClaims("a");
      act(() => { window.dispatchEvent(new Event("focus")); });
      await waitFor(() => expect(inQueue()).toEqual(["Ta", "Tb", "Tc", "Ta"]));
      await user.click(screen.getByRole("button", { name: zh.save }));
      await waitFor(() => expect(file.saved).toHaveLength(1));
      expect(JSON.parse(file.saved[0]).team_queue).toEqual(["a", "b", "c", "a"]);
    });

    test("an id of the queue that names no team is its own row, marked; the problem's click opens the Run tab on Mirror Dungeon and focuses it", async () => {
      file.text = text({ ...queue("a", "b", "c"), team_queue: ["a", "b", "c", "x"] });
      const user = userEvent.setup();
      render(<App start="teams" />);
      const extra = fill(zh["problem.queueExtra"], { name: "x" });
      await user.click(await within(await screen.findByRole("alert")).findByRole("button", { name: extra }));
      expect(screen.getByRole("tab", { name: new RegExp(`^${zh["tab.run"]}`) })).toHaveAttribute("aria-selected", "true");
      expect(rows()[3]).toHaveTextContent(/4\s*\? x$/); // after the wrong row's cross
      expect(within(rows()[3]).getByText(zh.hasProblem)).toBeInTheDocument();
      expect(document.activeElement).toBe(rows()[3].querySelector("[data-path='team_queue/3']"));
      // the task list's Mirror Dungeon row is the one picked, marked for the problem in its options
      const mirrorRow = within(document.querySelector(".task-list")!).getByText(zh["task.MirrorDungeon"]).closest("li")!;
      expect(mirrorRow).toHaveAttribute("aria-current", "true");
      expect(mirrorRow).toHaveClass("bad");
    });
  });

  test("the queue the Agent wrote is taken when the window comes back to the front; the list keeps its order", async () => {
    const user = userEvent.setup();
    render(<App start="teams" />);
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
    render(<App start="teams" />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    agentClaims("a");
    act(() => { window.dispatchEvent(new Event("focus")); });
    expect(await screen.findByText(zh.diskChanged)).toBeInTheDocument();
    expect(nameBox()).toHaveValue("Ta");
  });

  test("a save keeps the queue the Agent wrote under the unsaved edit", async () => {
    const user = userEvent.setup();
    render(<App start="teams" />);
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
    render(<App start="teams" />);
    await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
    await altMove(user, sideList().getAllByRole("listitem")[2], "ArrowUp");
    agentClaims("a");
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect([ids(saved), saved.team_queue]).toEqual([["a", "c", "b"], ["b", "c", "a"]]);
  });

  test("a poll and a save that read the Agent's write together save the Agent's queue", async () => {
    const user = userEvent.setup();
    render(<App start="teams" />);
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
    render(<App start="teams" />);
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
    render(<App start="teams" />);
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
    was.teams = was.teams.map((t: object) => ({ ...t, enabled: true })); // version 24 dropped it (#954)
    const old = { ...was, version: 20, ...cases.v20 }; // version 21 dropped these three sections (#782)
    file.text = text(old);
    file.beforeSave = () => { // the load's write-back meets the Agent's write, and a poll runs while it waits
      agentClaims("a");
      window.dispatchEvent(new Event("focus"));
    };
    const user = userEvent.setup();
    render(<App start="teams" />);
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
    render(<App start="teams" />);
    expect(await screen.findByText(zh.noTeams)).toBeInTheDocument();
    file.text = put;
    act(() => { window.dispatchEvent(new Event("focus")); });
    await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
  });

  test("New file writes over a file that does not parse", async () => {
    file.text = "{";
    const user = userEvent.setup();
    render(<App start="teams" />);
    await user.click(await screen.findByRole("button", { name: zh.newFile }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
  });

  test("a save then a switch of language shows no stale saved note", async () => {
    const user = userEvent.setup();
    render(<App start="teams" />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    await user.selectOptions(screen.getByRole("combobox", { name: zh.language }), "en_us");
    expect(document.querySelector(".status")).toHaveTextContent(/^Unsaved changes$/);
  });

  test("a file left half edited by hand is not saved over", async () => {
    const user = userEvent.setup();
    render(<App start="teams" />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    file.text = "{";
    await user.type(nameBox(), "!");
    await user.click(screen.getByRole("button", { name: zh.save }));
    expect(await screen.findByText(zh.saveConflict, { exact: false })).toHaveTextContent(zh.unsaved);
    expect(file.saved).toEqual([]);
  });
});
