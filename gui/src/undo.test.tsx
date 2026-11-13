// Undo (#664): the header's 復原 and Ctrl+Z take back the last edit, so a deleted plan or override row, or a wrong click on a
// game panel, is one step away from where it was. A text field keeps the browser's own Ctrl+Z for its text.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { TEXT } from "./i18n";
import { newSettings, type Settings } from "./model";

const file = vi.hoisted(() => ({ text: "" as string | null }));
vi.mock("./api", async (original) => {
  const api = await original<typeof import("./api")>();
  return {
    ...api,
    loadSettings: () => Promise.resolve(file.text),
    saveSettings: async (text: string) => { file.text = text; },
    rootDir: () => Promise.resolve("root"),
  };
});

const zh = TEXT.zh_tw;
const settings = (): Settings => ({
  ...newSettings(),
  deployment_order_plans: [{ id: "d1", name: "Bleed order", order: ["Yi Sang"] }],
  event_overrides: [{ question: "Q", option: "O" }],
});

async function open(tab: string) {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("tab", { name: tab }));
  return user;
}
const undoButton = () => screen.getByRole("button", { name: new RegExp(`^${zh.undo}`) });

beforeEach(() => { file.text = JSON.stringify(settings(), null, 2) + "\n"; });

describe("undo", () => {
  test("starts with nothing to take back", async () => {
    await open(zh["tab.deployment"]);
    expect(undoButton()).toBeDisabled();
  });

  test("復原 brings back a deleted plan, and the editor is as it was read", async () => {
    const user = await open(zh["tab.deployment"]);
    await user.click(screen.getByRole("button", { name: zh.remove }));
    expect(screen.queryByDisplayValue("Bleed order")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(zh.unsaved);

    await user.click(undoButton());
    expect(screen.getByDisplayValue("Bleed order")).toBeInTheDocument();
    expect(screen.getByRole("status")).not.toHaveTextContent(zh.unsaved);
    expect(undoButton()).toBeDisabled();
  });

  test("Ctrl+Z outside a text field takes back a deleted override row, one edit per press", async () => {
    const user = await open(zh["tab.events"]);
    await user.click(screen.getByRole("button", { name: `+ ${zh.add}` }));
    expect(screen.getAllByRole("button", { name: zh.remove })).toHaveLength(2);
    await user.click(screen.getAllByRole("button", { name: zh.remove })[0]);
    expect(screen.queryByDisplayValue("Q")).toBeNull();

    fireEvent.keyDown(document.body, { key: "z", ctrlKey: true });
    await waitFor(() => expect(screen.getByDisplayValue("Q")).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: zh.remove })).toHaveLength(2);
    fireEvent.keyDown(document.body, { key: "z", ctrlKey: true });
    await waitFor(() => expect(screen.getAllByRole("button", { name: zh.remove })).toHaveLength(1));
  });

  test("Ctrl+Z in a text field is the field's own undo, not the editor's", async () => {
    const user = await open(zh["tab.deployment"]);
    const name = screen.getByDisplayValue("Bleed order");
    await user.type(name, "!");
    fireEvent.keyDown(name, { key: "z", ctrlKey: true });
    expect(screen.getByDisplayValue("Bleed order!")).toBeInTheDocument();
  });

  test("typing a word is one step back, not one per letter", async () => {
    const user = await open(zh["tab.deployment"]);
    await user.type(screen.getByDisplayValue("Bleed order"), " two");
    await user.click(undoButton());
    expect(screen.getByDisplayValue("Bleed order")).toBeInTheDocument();
    expect(undoButton()).toBeDisabled();
  });

  test("after a save, 復原 takes back the saved edit and marks it unsaved", async () => {
    const user = await open(zh["tab.deployment"]);
    await user.click(screen.getByRole("button", { name: zh.remove }));
    await user.click(screen.getByRole("button", { name: zh.save }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(zh.saved));
    await user.click(undoButton());
    expect(screen.getByDisplayValue("Bleed order")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(zh.unsaved);
  });
});
