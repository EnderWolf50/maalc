// The team queue (#501): the order of the teams list is the queue the Agent rotates, and after a claim the Agent moves that
// team to the end of settings.json. The editor shows the order on disk, keeps the user's unsaved edits on top of it, and
// never saves its own stale order over the Agent's.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT } from "./i18n";
import { movedToEnd, newSettings, newTeam, rebase, type Settings } from "./model";

// lib.rs save_settings: refused when the file is no longer the text the editor last read or wrote.
const file = vi.hoisted(() => ({ text: "" as string | null, saved: [] as string[], beforeSave: undefined as (() => void) | undefined }));
vi.mock("./api", async (original) => {
  const api = await original<typeof import("./api")>();
  return {
    ...api,
    loadSettings: () => Promise.resolve(file.text),
    saveSettings: (text: string, expected: string | null) => {
      file.beforeSave?.();
      file.beforeSave = undefined;
      if (expected !== file.text) return Promise.reject(api.CHANGED);
      file.saved.push(text);
      file.text = text;
      return Promise.resolve();
    },
    rootDir: () => Promise.resolve("root"),
  };
});

const zh = TEXT.zh_tw;
const queue = (...ids: string[]): Settings => ({ ...newSettings(), teams: ids.map((id, n) => ({ ...newTeam(n + 1, `T${id}`), id })) });
const ids = (s: Settings) => s.teams.map((t) => t.id);
/** What the Agent writes after team `id` claimed: the same file, that team last (agent/team_queue.py requeue). */
const claimed = (s: Settings, id: string): Settings => ({ ...s, teams: [...s.teams.filter((t) => t.id !== id), ...s.teams.filter((t) => t.id === id)] });
const text = (s: Settings) => JSON.stringify(s, null, 2) + "\n";

describe("movedToEnd: the teams another writer moved to the end of the queue", () => {
  test.each([
    [["a", "b", "c"], ["b", "c", "a"], ["a"]], // the Agent after a's claim
    [["a", "b", "c"], ["a", "b", "c"], []],
    [["a", "b", "c", "d"], ["c", "d", "a", "b"], ["a", "b"]], // two claims, or the old cursor's turn (c first)
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

  test("an unsaved edit stays, in the order the Agent wrote", () => {
    const draft = structuredClone(base);
    draft.teams[1].name = "renamed";
    const next = rebase(base, draft, claimed(base, "a"));
    expect(ids(next)).toEqual(["b", "c", "a"]);
    expect(next.teams[0].name).toBe("renamed");
  });

  test("an unsaved reorder stays, with the claimed team moved to the end of it", () => {
    const draft = { ...base, teams: [base.teams[2], base.teams[0], base.teams[1]] }; // c dragged to the top
    expect(ids(rebase(base, draft, claimed(base, "a")))).toEqual(["c", "b", "a"]);
  });
});

describe("in the editor", () => {
  beforeEach(() => { file.text = text(queue("a", "b", "c")); file.saved = []; file.beforeSave = undefined; });
  const shown = () => within(document.querySelector("aside")!).getAllByRole("listitem").map((li) => li.textContent!.match(/T\w/)![0]);
  const nameBox = () => screen.getByRole("textbox", { name: zh.name });
  const agentClaims = (id: string) => { file.text = text(claimed(JSON.parse(file.text!), id)); };

  test("the teams tab says the list is the queue", async () => {
    render(<App />);
    expect(await screen.findByText(zh["teams.queue"])).toBeInTheDocument();
  });

  test("the order the Agent wrote shows when the window comes back to the front", async () => {
    render(<App />);
    await waitFor(() => expect(shown()).toEqual(["Ta", "Tb", "Tc"]));
    agentClaims("a");
    act(() => { window.dispatchEvent(new Event("focus")); });
    await waitFor(() => expect(shown()).toEqual(["Tb", "Tc", "Ta"]));
    expect(screen.getByText(zh.diskChanged)).toBeInTheDocument();
  });

  test("the team being edited stays in the editor when the Agent moves it", async () => {
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    agentClaims("a");
    act(() => { window.dispatchEvent(new Event("focus")); });
    await waitFor(() => expect(shown()).toEqual(["Tb", "Tc", "Ta"]));
    expect(nameBox()).toHaveValue("Ta");
  });

  test("a save keeps the order the Agent wrote under the unsaved edit", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    await user.type(nameBox(), "!");
    agentClaims("a"); // between two polls: the save itself finds it
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect(saved.teams.map((t) => t.name)).toEqual(["Tb", "Tc", "Ta!"]);
  });

  test("a save the Agent's write overtakes reads the file again and keeps that order too", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    await user.type(nameBox(), "!");
    file.beforeSave = () => agentClaims("a"); // after the save read the file, before it writes
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    const saved: Settings = JSON.parse(file.saved[0]);
    expect(saved.teams.map((t) => t.name)).toEqual(["Tb", "Tc", "Ta!"]);
    expect(screen.getByText(zh.saved)).toBeInTheDocument();
  });

  test("a file deleted while the editor is open is written again by a save", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(nameBox()).toHaveValue("Ta"));
    file.text = null;
    await user.type(nameBox(), "!");
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(file.saved).toHaveLength(1));
    expect(JSON.parse(file.saved[0]).teams[0].name).toBe("Ta!");
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
