// The window's title bar (#664): the system's own bar is hidden, and the header drags the window and holds its buttons.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import capability from "../src-tauri/capabilities/default.json";
import conf from "../src-tauri/tauri.conf.json";
import App from "./App";
import { TEXT } from "./i18n";
import css from "./index.css?raw";
import { newSettings, newTeam } from "./model";
import { cssRules } from "./testing";

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

describe("the window as it opens (#732)", () => {
  const [main] = conf.app.windows as { width: number; height: number; center?: boolean; preventOverflow?: boolean }[];

  test("is wide enough for a row of 6 sinners and a row of 5 starlight graces, and fits a 1920 x 1080 screen at 125 %", () => {
    // Measured in the built page (headless Edge, 2026-11-14): the team page holds 5 grace cards a row, each at least 216 px
    // so no title wraps (#726), from 1500 px wide; the 6 sinner tiles take a row at any width. 1536 x 864 is 1920 x 1080 at 125 %.
    expect(main.width).toBeGreaterThanOrEqual(1500);
    expect(main.width).toBeLessThanOrEqual(1536);
    expect(main.height).toBeLessThanOrEqual(864);
  });

  test("the width it opens at holds 5 grace cards a row on the team page, by the stylesheet's own sizes", () => {
    // Across the team page: the team list (`.split aside`), then the editor, where the starlight cards take their minimum
    // (`.graces`). The rest across (main's padding, the scrollbar, the gap after the list, the fieldset's and the starlight
    // page's padding and borders) is 132 px: measured in the built page, which holds 5 cards a row from 1500 px with the
    // cards at 216 px and the list at 240.
    const body = (sel: string) => cssRules(css).filter((r) => r.selector === sel).map((r) => r.body).join("\n");
    const card = Number(body(".graces").match(/minmax\((\d+)px/)![1]);
    const gap = Number(body(".graces").match(/gap:\s*(\d+)px/)![1]);
    const list = Number(body(".split aside").match(/width:\s*(\d+)px/)![1]);
    expect(main.width).toBeGreaterThanOrEqual(5 * card + 4 * gap + list + 132);
  });

  test("on a smaller screen it opens inside the screen's work area, centred", () => {
    expect(main.preventOverflow).toBe(true);
    expect(main.center).toBe(true);
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

test("while the settings still load, a window button that fails shows its reason alone", async () => {
  const api = await import("./api");
  const load = vi.spyOn(api, "loadSettings").mockReturnValue(new Promise(() => {}));
  const spy = vi.spyOn(api, "minimizeWindow").mockRejectedValue("no permission");
  try {
    const user = userEvent.setup();
    render(<App />);
    await user.click(button(zh["win.minimize"]));
    const why = await screen.findByText(zh.loadError);
    expect(why.parentElement!.querySelector("pre")!.textContent).toBe("no permission");
  } finally {
    spy.mockRestore();
    load.mockRestore();
  }
});

test("on the load error screen, a window button that fails adds its reason under the file's, which stays", async () => {
  win.text = "{ not json";
  const api = await import("./api");
  const spy = vi.spyOn(api, "minimizeWindow").mockRejectedValue("no permission");
  try {
    const user = userEvent.setup();
    render(<App />);
    const why = await screen.findByText(zh.loadError);
    await user.click(button(zh["win.minimize"]));
    const pre = why.parentElement!.querySelector("pre")!;
    await waitFor(() => expect(pre).toHaveTextContent("no permission"));
    expect(pre.textContent).toMatch(/JSON|Unexpected|token|position/i);
  } finally {
    spy.mockRestore();
  }
});
