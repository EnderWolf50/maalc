// The team queue (#501, #803): team_queue in settings.json is the queue the Agent rotates, and after a claim the Agent moves
// that team to its end. The team list is the user's to arrange: its drag and its Alt moves leave the queue alone. A team added goes
// last in both, a team deleted leaves both. The editor takes the queue on disk, keeps the user's unsaved edits on top of it,
// and never saves its own stale queue over the Agent's. The queue is shown and arranged in the Mirror Dungeon task's options
// on the Run tab, where each row's flag sets run.start_team (#878, spec #871 「隊伍佇列（只在鏡牢選項裡）」).
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App, { TABS } from "./App";
import { TEXT, fill } from "./i18n";
import { addTeam, movedToEnd, newSettings, newTeam, rebase, type Settings } from "./model";
import { applyEdits, cases, type Edit as FileEdit } from "./settingsCases";
import css from "./index.css?raw";
import { TeamsTab } from "./Teams";
import { altMove, cssValueOf, dragOnto, pickInList, renderEditor, sideList } from "./testing";

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
/** Team `name`'s start flag in the queue (its name says what a press does). */
const flag = (name: string, on = false) =>
  within(queueFrame()).getByRole("button", { name: fill(zh[on ? "queue.flag_clear" : "queue.flag_set"], { name }) });

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

  test("Alt with an arrow in the list moves a team in the list, not in the queue", async () => {
    const r = renderEditor(<TeamsTab />, apart());
    await altMove(r.user, rows()[2], "ArrowUp");
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "c", "b"], ["c", "a", "b"]]);
    await altMove(r.user, rows()[0], "ArrowDown");
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

  test("the tab has no queue; a line under the list says where the queue is arranged (#878)", () => {
    renderEditor(<TeamsTab />, apart());
    expect(screen.queryByRole("group", { name: zh["queue.title"] })).toBeNull();
    expect(screen.queryByRole("list", { name: zh["queue.title"] })).toBeNull();
    const note = sideList().getByText(zh["teams.order_note"]);
    expect(note).toBeVisible();
    expect(zh["teams.order_note"]).toBe("清單順序只是顯示用。哪一支先出戰，在「執行」分頁點鏡牢，用「隊伍佇列」排。新增的隊伍排在最後。");
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

  test("lists every team in the queue's order: its place, name and slot, and its usage only when kept to one difficulty", async () => {
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
    // the slot, the usage, the mark and the flag in columns every row shares (subgrid), the slot's numerals of one width
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

  test("a disabled team stays in its place, struck through in the muted ink, read as off, its tooltip saying it is passed over", async () => {
    const s = queue("a", "b", "c");
    s.teams[1].enabled = false;
    await mirror(s);
    const [a, b] = rows();
    expect(b).toHaveTextContent(/^2\s*Tb/);
    const name = within(b).getByText("Tb");
    expect([cssValueOf(css, name, "color"), cssValueOf(css, name, "text-decoration")]).toEqual(["var(--muted)", "line-through"]);
    expect(cssValueOf(css, within(a).getByText("Ta"), "text-decoration")).toBeUndefined();
    expect(within(b).getByText(zh["team.off_read"])).toHaveClass("sr-only"); // （停用） for a screen reader, no tag on the page
    expect(a).not.toHaveTextContent(zh["team.off_read"]);
    expect(b.querySelector(".qtag")).toBeNull();
    expect(b.querySelector("[title]")).toHaveAttribute("title", zh["queue.off_tip"]);
    expect(cssValueOf(css, b, "opacity")).toBeUndefined(); // the row itself is not faded: its words keep their contrast
  });

  // The next new run of each difficulty the task plays (run.difficulty; auto plays either) is the first enabled team in the
  // queue whose usage fits it (agent/team_queue.py pick_team), counted from the start team when one is set (headed).
  /** The next-run mark of each row: "" for none, 下一局 alone, or with the difficulty's plate. */
  const marks = () => rows().map((li) => li.textContent!.match(new RegExp(`${zh["queue.next"]}(${zh["difficulty.normal"]}|${zh["difficulty.hard"]})?`))?.[0] ?? "");
  const NEXT = zh["queue.next"], NORMAL = NEXT + zh["difficulty.normal"], HARD = NEXT + zh["difficulty.hard"];
  type Edit = Partial<Pick<Settings["teams"][number], "enabled" | "usage">>;
  test.each<[string, Edit[], Partial<Settings["run"]>, string[]]>([
    ["one team plays both: 下一局 alone", [{ enabled: false }, {}, { usage: "hard_only" }], {}, ["", NEXT, ""]],
    ["hard and normal play different teams: 下一局 with each one's plate",
      [{ enabled: false, usage: "any" }, { usage: "hard_only" }, { usage: "any" }], {}, ["", HARD, NORMAL]],
    ["a team kept to Normal first, then one for both", [{ usage: "normal_only" }, {}, {}], {}, [NORMAL, HARD, ""]],
    ["no team to play: no mark", [{ enabled: false }, { enabled: false }, { enabled: false }], {}, ["", "", ""]],
    ["only Hard has a team: its mark says Hard", [{ usage: "hard_only" }, { enabled: false }, { usage: "hard_only" }], {}, [HARD, "", ""]],
    ["the task plays Hard only: Hard's team alone, no plate", [{ usage: "normal_only" }, {}, {}], { difficulty: "hard" }, ["", NEXT, ""]],
    ["the task plays Normal only: Normal's team alone, no plate", [{ usage: "hard_only" }, {}, {}], { difficulty: "normal" }, ["", NEXT, ""]],
    ["a start team: counted from it", [{}, {}, {}], { start_team: "b" }, ["", "", NEXT]],
    ["a start team kept to Hard: Hard from it, Normal from the queue's head",
      [{}, {}, { usage: "hard_only" }], { start_team: "b" }, [NORMAL, "", HARD]],
  ])("%s", async (_, edits, run, expected) => {
    const s = { ...queue("a", "b", "c"), team_queue: ["c", "a", "b"] }; // the list's order is not the queue's
    const inQueue = s.team_queue.map((id) => s.teams.find((x) => x.id === id)!);
    edits.forEach((e, j) => Object.assign(inQueue[j], e));
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

  // tests/settings_cases.json next_run: the agent's pick_team, headed by the start team, gives the same teams
  // (tests/test_team_queue.py).
  test.each(cases.next_run as { name: string; edits: FileEdit[]; hard: string | null; normal: string | null }[])(
    "the marks name the teams the agent picks: $name", async ({ edits, hard, normal }) => {
      const s = applyEdits(cases.valid, edits) as unknown as Settings;
      const mark = (id: string) => (hard === id && normal === id ? NEXT : hard === id ? HARD : normal === id ? NORMAL : "");
      await mirror(s);
      expect(marks()).toEqual(s.team_queue.map(mark));
    });

  test("Alt with an arrow in it moves a team in the queue, not in the list", async () => {
    const r = await mirror(queue("a", "b", "c"));
    await altMove(r.user, rows()[2], "ArrowUp");
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c"], ["a", "c", "b"]]);
    await altMove(r.user, rows()[0], "ArrowDown");
    expect([ids(r.settings()), r.settings().team_queue]).toEqual([["a", "b", "c"], ["c", "a", "b"]]);
    expect(shown()).toEqual([expect.stringMatching(/^1 Tc/), expect.stringMatching(/^2 Ta/), expect.stringMatching(/^3 Tb/)]);
  });

  test("no 「這次從哪一支隊伍開始」 pick and no 照隊伍佇列 lines: the flags are the start team", async () => {
    await mirror(queue("a", "b"));
    expect(screen.queryByRole("combobox", { name: new RegExp(zh["run.start_team"]) })).toBeNull();
    for (const gone of ["照隊伍佇列開始", "改回照隊伍佇列", zh["run.start_team"]]) expect(document.body).not.toHaveTextContent(gone);
  });
});

describe("the start team's flag on each queue row (#878, run.start_team)", () => {
  test("a press sets the start team, pressed and named to clear it; a second press clears it", async () => {
    const r = await mirror(queue("a", "b"));
    expect(flag("Ta")).toHaveAttribute("aria-pressed", "false");
    await r.user.click(flag("Ta"));
    expect(r.settings().run.start_team).toBe("a");
    expect(flag("Ta", true)).toHaveAttribute("aria-pressed", "true");
    expect(r.settings().team_queue).toEqual(["a", "b"]); // the queue itself is the Agent's to move (to_head)
    await r.user.click(flag("Ta", true));
    expect(r.settings().run.start_team).toBeNull();
    expect(flag("Ta")).toHaveAttribute("aria-pressed", "false");
  });

  test("one team at most: a press on another moves the flag there", async () => {
    const r = await mirror(queue("a", "b"));
    await r.user.click(flag("Ta"));
    await r.user.click(flag("Tb"));
    expect(r.settings().run.start_team).toBe("b");
    expect(within(queueFrame()).getAllByRole("button", { pressed: true })).toEqual([flag("Tb", true)]);
  });

  test("a disabled team's flag sets nothing: unavailable, faint, the no-entry pointer, its words saying why", async () => {
    const s = queue("a", "b");
    s.teams[1].enabled = false;
    const r = await mirror(s);
    expect(flag("Tb")).toHaveAttribute("aria-disabled", "true");
    expect(flag("Ta")).not.toHaveAttribute("aria-disabled");
    await r.user.click(flag("Tb"));
    expect(r.settings().run.start_team).toBeNull();
    expect(flag("Tb")).toHaveAttribute("aria-pressed", "false");
    expect([cssValueOf(css, flag("Tb"), "opacity"), cssValueOf(css, flag("Tb"), "cursor")]).toEqual(["0.3", "not-allowed"]);
    expect(cssValueOf(css, flag("Ta"), "opacity")).toBeUndefined(); // an enabled team's, undimmed
    expect(cssValueOf(css, flag("Tb"), "color", flag("Tb"))).toBe("var(--muted)"); // the pointer does not light it
    // its words still float over it, under the pointer and under the keyboard's focus, which still reaches it
    expect(flag("Tb")).toHaveAttribute("data-tip", zh["queue.flag_tip_off"]);
    expect(cssValueOf(css, flag("Tb"), "opacity", flag("Tb"), "::after")).toBe("1");
    expect(cssValueOf(css, flag("Tb"), "opacity", { focus: flag("Tb") }, "::after")).toBe("1");
    expect(flag("Tb")).toBeEnabled();
    expect(zh["queue.flag_tip_off"]).toBe("隊伍停用中，不能從這支開始");
  });

  test("its words float over it while the pointer or the keyboard's focus is on it; no native tooltip of the list's under them", async () => {
    const r = await mirror(queue("a", "b"));
    expect(flag("Ta")).toHaveAttribute("data-tip", zh["queue.flag_tip"]);
    expect(flag("Ta")).toHaveAttribute("title", ""); // the list's 拖曳 tooltip would show over the words
    expect(cssValueOf(css, flag("Ta"), "opacity", false, "::after")).toBe("0");
    expect(cssValueOf(css, flag("Ta"), "opacity", flag("Ta"), "::after")).toBe("1");
    expect(cssValueOf(css, flag("Ta"), "opacity", { focus: flag("Ta") }, "::after")).toBe("1");
    // drawn words only: with no alternative text, the accessibility tree took them into the row's name (the real window, UIA)
    expect(cssValueOf(css, flag("Ta"), "content", false, "::after")).toBe('attr(data-tip) / ""');
    await r.user.click(flag("Ta"));
    expect(flag("Ta", true)).toHaveAttribute("data-tip", zh["queue.flag_tip_on"]);
    expect(zh["queue.flag_tip"]).toBe("這次從這支開始");
    expect(zh["queue.flag_tip_on"]).toBe("這次從這支開始（再按取消）");
  });

  test("lit, a line under the queue says the flag stays in the file; none while no flag is lit", async () => {
    const r = await mirror(queue("a", "b"));
    expect(screen.queryByText(zh["queue.flag_kept"])).toBeNull();
    await r.user.click(flag("Tb"));
    expect(within(queueFrame()).getByText(zh["queue.flag_kept"])).toBeVisible();
    expect(zh["queue.flag_kept"]).toBe("旗子會存進設定檔，每次開始都會再排一次，用完記得改回。");
  });

  test("a flag already on a disabled team (a hand edit) has no effect, dimmed and muted; a press clears it, and then sets nothing", async () => {
    const s = queue("a", "b");
    s.teams[1].enabled = false;
    s.run.start_team = "b";
    const r = await mirror(s);
    expect(flag("Tb", true)).not.toHaveAttribute("aria-disabled");
    expect(flag("Tb", true)).toHaveAttribute("data-tip", zh["queue.flag_tip_off_on"]);
    expect([cssValueOf(css, flag("Tb", true), "opacity"), cssValueOf(css, flag("Tb", true), "color")]).toEqual(["0.5", "var(--muted)"]);
    expect(cssValueOf(css, flag("Tb", true), "opacity", flag("Tb", true))).toBe("1"); // lit under the pointer: a press does something
    expect(screen.queryByText(zh["queue.flag_kept"])).toBeNull(); // the flag has no effect, so it costs nothing
    await r.user.click(flag("Tb", true));
    expect(r.settings().run.start_team).toBeNull();
    expect(flag("Tb")).toHaveAttribute("aria-disabled", "true");
    await r.user.click(flag("Tb"));
    expect(r.settings().run.start_team).toBeNull();
    expect(zh["queue.flag_tip_off_on"]).toBe("隊伍停用中，旗子沒有作用（再按取消）");
  });

  test("a lit flag on a team enabled again counts again: amber, its usual words, and the line under the queue", async () => {
    const s = queue("a", "b");
    s.teams[1].enabled = false;
    s.run.start_team = "b";
    await mirror(s);
    expect(flag("Tb", true)).toHaveAttribute("data-tip", zh["queue.flag_tip_off_on"]);
    cleanup();
    s.teams[1].enabled = true;
    await mirror(s);
    expect(flag("Tb", true)).toHaveAttribute("data-tip", zh["queue.flag_tip_on"]);
    expect(cssValueOf(css, flag("Tb", true), "color")).toBe("var(--accent)");
    expect(within(queueFrame()).getByText(zh["queue.flag_kept"])).toBeVisible();
  });

  test("disabling the start team in the Teams tab takes its flag off at once; enabling it again does not put it back", async () => {
    const s = queue("a", "b");
    s.run.start_team = "b";
    const r = renderEditor(<TeamsTab />, s);
    const enabled = () => screen.getByRole("checkbox", { name: zh["team.enabled"] });
    await pickInList(r.user, "Ta");
    await r.user.click(enabled()); // another team off: the flag stays
    expect([r.settings().teams[0].enabled, r.settings().run.start_team]).toEqual([false, "b"]);
    await pickInList(r.user, "Tb");
    await r.user.click(enabled());
    expect([r.settings().teams[1].enabled, r.settings().run.start_team]).toEqual([false, null]);
    await r.user.click(enabled());
    expect([r.settings().teams[1].enabled, r.settings().run.start_team]).toEqual([true, null]);
  });

  test("a start team deleted since has no row and no flag: nothing under the queue, no button but the rows' flags", async () => {
    const s = queue("a", "b");
    s.run.start_team = "gone";
    await mirror(s);
    expect(within(queueFrame()).queryAllByRole("button", { pressed: true })).toEqual([]);
    expect(queueFrame().querySelector("p")).toBeNull();
    expect(within(queueFrame()).getAllByRole("button").map((b) => b.getAttribute("aria-label")))
      .toEqual([fill(zh["queue.flag_set"], { name: "Ta" }), fill(zh["queue.flag_set"], { name: "Tb" })]);
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
    s.teams[0].enabled = false;
    renderEditor(<RunTab />, s);
    expect(nextLine(mirrorRows()[0])).toHaveTextContent(new RegExp(`^${zh["queue.next"]}\\s*${zh["queue.no_team"]}$`));
  });

  test("a start team set: counted from it, and a lit flag after the names", async () => {
    const s = queue("a", "b");
    s.run.start_team = "b";
    renderEditor(<RunTab />, s);
    const line = nextLine(mirrorRows()[0])!;
    expect(line).toHaveTextContent(new RegExp(`^${zh["queue.next"]}\\s*Tb\\s*${zh["queue.flag_on"]}$`));
  });

  test.each([["disabled", "b"], ["deleted", "gone"]])("a start team %s: no lit flag on the row, the queue as with no flag", async (_, id) => {
    const s = { ...queue("a", "b", "c"), team_queue: ["c", "a", "b"] };
    s.teams[1].enabled = id !== "b";
    s.run.start_team = id;
    renderEditor(<RunTab />, s);
    expect(nextLine(mirrorRows()[0])).toHaveTextContent(new RegExp(`^${zh["queue.next"]}\\s*Tc$`));
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

    test("a flag on a team deleted since goes with the next save, which leaves nothing unsaved (#878)", async () => {
      const s = queue("a", "b", "c");
      s.run.start_team = "b";
      file.text = text(s);
      const user = userEvent.setup();
      render(<App start="teams" />);
      await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
      await pickInList(user, "Tb");
      await user.click(screen.getByRole("button", { name: zh.remove }));
      await user.click(screen.getByRole("button", { name: zh.save }));
      await waitFor(() => expect(file.saved).toHaveLength(1));
      const saved: Settings = JSON.parse(file.saved[0]);
      expect([ids(saved), saved.team_queue, saved.run.start_team]).toEqual([["a", "c"], ["a", "c"], null]);
      await waitFor(() => expect(document.querySelector(".status")).not.toHaveTextContent(zh.unsaved));
    });

    test("the start team disabled in the Teams tab is saved with no flag, and the Mirror Dungeon options show none lit (#878)", async () => {
      const s = queue("a", "b", "c");
      s.run.start_team = "b";
      file.text = text(s);
      const user = userEvent.setup();
      render(<App start="teams" />);
      await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
      await pickInList(user, "Tb");
      await user.click(screen.getByRole("checkbox", { name: zh["team.enabled"] }));
      await user.click(screen.getByRole("button", { name: zh.save }));
      await waitFor(() => expect(file.saved).toHaveLength(1));
      const saved: Settings = JSON.parse(file.saved[0]);
      expect([saved.teams[1].enabled, saved.run.start_team]).toEqual([false, null]);
      await user.click(screen.getByRole("tab", { name: new RegExp(`^${zh["tab.run"]}`) }));
      await showMirror(user);
      expect(within(queueFrame()).queryAllByRole("button", { pressed: true })).toEqual([]);
      expect(flag("Tb")).toHaveAttribute("aria-disabled", "true");
    });

    test("a flag pressed is saved as run.start_team, and the queue as it was", async () => {
      const user = await openMirror();
      await user.click(flag("Tb"));
      await user.click(screen.getByRole("button", { name: zh.save }));
      await waitFor(() => expect(file.saved).toHaveLength(1));
      const saved: Settings = JSON.parse(file.saved[0]);
      expect([saved.run.start_team, saved.team_queue]).toEqual(["b", ["a", "b", "c"]]);
    });

    test.each([
      ["the Agent moves a claimed team to the end", (s: Settings) => claimed(s, "a"), ["Tb", "Tc", "Ta"]],
      ["a task's start team is put first (#802)", (s: Settings) => ({ ...s, team_queue: ["c", "a", "b"] }), ["Tc", "Ta", "Tb"]],
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
