// The editor's shell (App.tsx): the main tabs from the keyboard, and the save state in the header when a save is refused.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT, fill } from "./i18n";
import { newSettings, newTeam } from "./model";

const zh = TEXT.zh_tw;
const file = vi.hoisted(() => ({ text: "", saved: [] as string[], fail: "" }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: (text: string) => {
    if (file.fail) return Promise.reject(new Error(file.fail));
    file.saved.push(text);
    return Promise.resolve();
  },
  rootDir: () => Promise.resolve("root"),
}));

/** Two enabled teams on game team slot 1: a save is refused (validate.ts crossCheck). */
function clash() {
  const s = newSettings();
  s.teams = [newTeam(1, "Ta"), newTeam(2, "Tb")];
  s.teams[1].game_team = 1;
  return JSON.stringify(s, null, 2) + "\n";
}

beforeEach(() => { file.text = JSON.stringify(newSettings(), null, 2) + "\n"; file.saved = []; file.fail = ""; });

test("the arrow keys move along the main tabs and open the one they reach; Home and End go to the ends", async () => {
  const user = userEvent.setup();
  render(<App />);
  const teams = await screen.findByRole("tab", { name: zh["tab.teams"] });
  expect(teams).toHaveAttribute("tabindex", "0");
  expect(screen.getByRole("tab", { name: zh["tab.run"] })).toHaveAttribute("tabindex", "-1");
  teams.focus();
  await user.keyboard("{ArrowRight}");
  const gifts = screen.getByRole("tab", { name: zh["tab.gifts"] });
  expect(gifts).toHaveAttribute("aria-selected", "true");
  expect(gifts).toHaveFocus();
  await user.keyboard("{ArrowLeft}{ArrowLeft}");
  expect(screen.getByRole("tab", { name: zh["tab.run"] })).toHaveFocus();
  await user.keyboard("{End}");
  expect(screen.getByRole("tab", { name: zh["tab.daily"] })).toHaveAttribute("aria-selected", "true");
  await user.keyboard("{Home}");
  expect(screen.getByRole("tab", { name: zh["tab.run"] })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", screen.getByRole("tab", { name: zh["tab.run"] }).id);
});

test("with nothing edited the header says there is nothing to save", async () => {
  render(<App />);
  await screen.findByRole("button", { name: zh.save });
  expect(document.querySelector(".status")).toHaveAttribute("data-state", "clean");
  expect(document.querySelector(".status")).toHaveTextContent(zh["saveState.clean"]);
});

test("a write that fails shows as a failure in the header, not as plain unsaved changes; the next good save clears it", async () => {
  const s = newSettings();
  s.teams = [newTeam(1, "Ta")];
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
  ok.teams = [newTeam(1, "Ta"), newTeam(2, "Tb")];
  file.text = JSON.stringify(ok, null, 2) + "\n";
  const user = userEvent.setup();
  render(<App />);
  const save = await screen.findByRole("button", { name: zh.save });
  await user.click(save);
  await waitFor(() => expect(document.querySelector(".status")).toHaveAttribute("data-state", "saved"));
  await user.click(screen.getAllByRole("listitem")[1]);
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

test("a problem made before any save already says Save must wait, on the plate and on Save; the fields are not marked yet", async () => {
  const ok = newSettings();
  ok.teams = [newTeam(1, "Ta"), newTeam(2, "Tb")];
  file.text = JSON.stringify(ok, null, 2) + "\n";
  const user = userEvent.setup();
  render(<App />);
  const save = await screen.findByRole("button", { name: zh.save });
  await user.click(screen.getAllByRole("listitem")[1]);
  const slot = screen.getByRole("spinbutton", { name: zh["team.game_team"] });
  fireEvent.change(slot, { target: { value: "1" } });
  const plate = document.querySelector(".status")!;
  expect(plate).toHaveAttribute("data-state", "blocked");
  expect(plate).toHaveTextContent(fill(zh["saveState.toFix"], { n: 1 }));
  expect(save).toHaveClass("refused");
  expect(save).not.toHaveClass("armed");
  expect(slot).not.toHaveAttribute("aria-invalid");
  expect(screen.queryByRole("alert")).toBeNull();
});

describe("Revert", () => {
  const edited = async () => {
    const ok = newSettings();
    ok.teams = [newTeam(1, "Ta")];
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
