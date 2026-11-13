// The window's title bar (#664): the system's own bar is hidden, and the header drags the window and holds its buttons.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import capability from "../src-tauri/capabilities/default.json";
import conf from "../src-tauri/tauri.conf.json";
import App from "./App";
import { TEXT } from "./i18n";
import { newSettings, newTeam } from "./model";

const zh = TEXT.zh_tw;
// The window as Tauri runs it: a close request goes to the page's listener first, and the window goes only when the page lets
// it (api.ts onCloseRequested); the page hears whether the window is maximised (api.ts onMaximized).
const win = vi.hoisted(() => ({
  text: "", keepOpen: undefined as (() => boolean) | undefined, maximized: undefined as ((on: boolean) => void) | undefined,
  closed: 0, minimized: 0, toggled: 0,
}));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(win.text),
  saveSettings: () => Promise.resolve(),
  rootDir: () => Promise.resolve("root"),
  onCloseRequested: (keepOpen: () => boolean) => { win.keepOpen = keepOpen; return () => {}; },
  closeWindow: () => { win.closed++; return Promise.resolve(); },
  requestClose: () => { if (!win.keepOpen?.()) win.closed++; return Promise.resolve(); },
  minimizeWindow: () => { win.minimized++; return Promise.resolve(); },
  toggleMaximize: () => { win.toggled++; return Promise.resolve(); },
  onMaximized: (seen: (on: boolean) => void) => { win.maximized = seen; seen(false); return () => {}; },
}));

beforeEach(() => {
  const s = newSettings();
  s.teams = [newTeam(1, "Ta")];
  win.text = JSON.stringify(s, null, 2) + "\n";
  Object.assign(win, { keepOpen: undefined, maximized: undefined, closed: 0, minimized: 0, toggled: 0 });
});

const button = (name: string) => screen.getByRole("button", { name });
const shown = async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("textbox", { name: zh.name });
  return user;
};

describe("the title bar", () => {
  test("the system's bar is hidden: the window has no decorations and keeps a size the header fits in", () => {
    const [main] = conf.app.windows as { decorations?: boolean; minWidth?: number; minHeight?: number }[];
    expect(main.decorations).toBe(false);
    expect(main.minWidth).toBeGreaterThan(0);
    expect(main.minHeight).toBeGreaterThan(0);
  });

  test("the window may drag, minimise, maximise and close itself", () => {
    // core:default holds none of these; without them each button and the drag fail with a permission error
    for (const p of ["start-dragging", "minimize", "toggle-maximize", "close"]) {
      expect(capability.permissions).toContain(`core:window:allow-${p}`);
    }
  });

  test("the header drags the window from its empty parts and its labels, not from its controls", async () => {
    await shown();
    const header = document.querySelector("header")!;
    // Tauri's drag script (drag.js): "deep" drags from anywhere inside but a button, a select, a label or a tab stop
    expect(header).toHaveAttribute("data-tauri-drag-region", "deep");
    for (const el of header.querySelectorAll("[data-tauri-drag-region]")) expect(el).toBe(header);
  });

  test("minimise and maximise are buttons with names that act on the window", async () => {
    const user = await shown();
    await user.click(button(zh["win.minimize"]));
    expect(win.minimized).toBe(1);
    await user.click(button(zh["win.maximize"]));
    expect(win.toggled).toBe(1);
  });

  test("maximised, the middle button restores, and says so", async () => {
    await shown();
    act(() => win.maximized!(true));
    expect(button(zh["win.restore"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: zh["win.maximize"] })).toBeNull();
    act(() => win.maximized!(false));
    expect(button(zh["win.maximize"])).toBeInTheDocument();
  });

  test("the buttons follow Save in the tab order, so the keyboard reaches them", async () => {
    const user = await shown();
    button(zh.save).focus();
    await user.tab();
    expect(button(zh["win.minimize"])).toHaveFocus();
    await user.tab();
    expect(button(zh["win.maximize"])).toHaveFocus();
    await user.tab();
    expect(button(zh["win.close"])).toHaveFocus();
  });

  test("close with nothing unsaved closes the window", async () => {
    const user = await shown();
    await user.click(button(zh["win.close"]));
    expect(win.closed).toBe(1);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("close with unsaved changes asks first, as Alt+F4 does, and keeps the window open", async () => {
    const user = await shown();
    await user.type(screen.getByRole("textbox", { name: zh.name }), "!");
    await user.click(button(zh["win.close"]));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(zh.closeAsk);
    expect(win.closed).toBe(0);
    await user.click(button(zh.closeDiscard));
    await waitFor(() => expect(win.closed).toBe(1));
  });
});

describe("a settings file that does not read", () => {
  beforeEach(() => { win.text = "{ not json"; });

  test("keeps the title bar: it drags the window, and its buttons and a Close beside New file close it", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText(zh.loadError)).toBeInTheDocument();
    expect(document.querySelector("header")).toHaveAttribute("data-tauri-drag-region", "deep");
    expect(button(zh["win.minimize"])).toBeInTheDocument();
    await user.click(within(document.querySelector("main")!).getByRole("button", { name: zh["win.close"] }));
    expect(win.closed).toBe(1);
  });
});
